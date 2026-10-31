"""Construye y ejecuta el crew de TertulIA por pasos.

El grafo (LangGraph, David) decide el orden y el bucle de revisión. Cada nodo del
grafo llama a ``run_step()`` con el nombre de su paso, y el crew ejecuta solo las
tareas de ese paso:

    nodo research  -> run_step("research")  -> research_task + vision_task (en paralelo)
    nodo analyst   -> run_step("analysis")  -> analysis_task
    nodo writer    -> run_step("writing")   -> writing_task
    nodo reviewer  -> run_step("review")    -> review_task

No usamos el decorador @CrewBase de CrewAI porque está pensado para ejecutar
todas las tareas de golpe. Aquí construimos a mano un Crew pequeño por paso.

Las herramientas de cada agente salen de agent_tools.py (DEFAULT_TOOLS). Los tests
pasan herramientas falsas con el parámetro ``tools`` para no arrancar servidores.
"""

import logging
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml
from crewai import LLM, Agent, Crew, Process, Task
from crewai.llms.base_llm import BaseLLM
from crewai.tools import BaseTool

from tertulia.crew.agent_tools import default_tools
from tertulia.crew.inputs import NO_IMAGES

logger = logging.getLogger(__name__)

# Herramientas por agente: {"researcher": [...], "analyst": [...]}
ToolsByAgent = Mapping[str, list[BaseTool]]

CONFIG_DIR = Path(__file__).resolve().parent / "config"

# Paso del crew -> tareas que ejecuta, en orden
STEPS: dict[str, tuple[str, ...]] = {
    "research": ("research_task", "vision_task"),
    "analysis": ("analysis_task",),
    "writing": ("writing_task",),
    "review": ("review_task",),
}

APPROVED = "APROBADO"


# Se añade a la tarea de un agente que no tiene herramientas. Motivo: en la prueba
# real del 23 oct, el Investigador sin herramientas inventó cifras, fuentes y enlaces
# aunque la tarea le pedía no hacerlo. El aviso le dice explícitamente qué NO puede hacer.
NO_TOOLS_NOTE = (
    "IMPORTANTE: en esta ejecución NO tienes ninguna herramienta. No puedes consultar "
    "páginas web, mapas, APIs ni ninguna otra fuente, y no debes escribir datos de "
    "memoria. No escribas cifras, nombres de negocios ni enlaces. Responde "
    '"sin dato" a cada pregunta que necesite un dato.'
)


def load_config() -> tuple[dict, dict]:
    """Lee agents.yaml y tasks.yaml."""

    def read(name: str) -> dict:
        return yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8"))

    return read("agents.yaml"), read("tasks.yaml")


# Gemini (capa gratuita): límite de peticiones por minuto. Comprobado en CrewAI 1.15.28
# y google-genai 1.65: CrewAI usa el SDK de Google (no litellm) y, sin estas opciones,
# un error 429 NO se reintenta y una llamada sin respuesta espera sin límite (23 oct).
LLM_TIMEOUT_S = 90  # por intento
LLM_RETRY_ATTEMPTS = 5  # contando el primero
LLM_RETRY_FIRST_WAIT_S = 5  # esperas 5, 10, 20, 40 s: cubren una ventana de 1 minuto
LLM_RETRY_MAX_WAIT_S = 60


def _gemini_client_params() -> dict:
    """Tiempo límite y reintentos con espera creciente para 408, 429 y errores 5xx."""
    from google.genai import types

    return {
        "http_options": types.HttpOptions(
            timeout=LLM_TIMEOUT_S * 1000,  # el SDK de Google usa milisegundos
            retry_options=types.HttpRetryOptions(
                attempts=LLM_RETRY_ATTEMPTS,
                initial_delay=LLM_RETRY_FIRST_WAIT_S,
                max_delay=LLM_RETRY_MAX_WAIT_S,
            ),
        )
    }


def build_llm(provider: str, model_name: str, api_key: str | None = None) -> LLM:
    """Crea el modelo de lenguaje. No hace ninguna llamada: solo lo configura.

    Los valores vienen de config/settings.py (David), p. ej. ``"gemini"`` y
    ``"gemini-3.5-flash-lite"``. Cambiar de modelo no obliga a tocar este archivo.
    Con Gemini se añaden tiempo límite y reintentos (ver LLM_RETRY_*).
    Nota: ``LLM(max_retries=...)`` no tiene efecto con Gemini en CrewAI 1.15.28.
    """
    extra = {"client_params": _gemini_client_params()} if provider == "gemini" else {}
    llm = LLM(model=f"{provider}/{model_name}", api_key=api_key or None, **extra)
    if provider == "gemini" and hasattr(llm, "thinking_config"):
        # CrewAI 1.15.28 auto-habilita ThinkingConfig para modelos con versión ≥ 2.5
        # (gemini-3.5 supera el umbral). gemini-3.5-flash-lite rechaza thinking_config
        # con 400 INVALID_ARGUMENT, así que se borra después de construir el objeto.
        # validate_assignment=False en GeminiCompletion permite la asignación directa.
        llm.thinking_config = None
    return llm


def llm_from_settings() -> LLM:
    """Atajo para el grafo: crea el modelo con los valores de config/settings.py."""
    from config.settings import settings  # se importa aquí: config/ está fuera de src/

    return build_llm(
        settings.LLM_PROVIDER,
        settings.LLM_MODEL_NAME,
        settings.LLM_API_KEY.get_secret_value(),
    )


# Si no hay fotos, la tarea de visión no llama al modelo: su respuesta es esta.
NO_IMAGES_ANSWER = "sin imágenes"
# Cada foto es una llamada a la herramienta y cada llamada gasta un paso del agente
# (max_iter). Con 5 pasos solo se analizaban 5 de 10 fotos: se dan pasos de sobra.
VISION_EXTRA_STEPS = 2
# Si la visión falla, la investigación se conserva y la visión responde esto (sin inventar).
VISION_FAILED_ANSWER = "No se pudieron analizar las imágenes"


def build_step_crew(step: str, llm: BaseLLM, tools: ToolsByAgent | None = None) -> Crew:
    """Crew con solo las tareas de ``step`` y los agentes que las hacen.

    ``tools``: herramientas que SUSTITUYEN a las de agent_tools.py para algunos agentes.
    Un agente que no aparece en el diccionario recibe sus herramientas por defecto;
    para dejar a un agente sin herramientas hay que pasar una lista vacía.
    Ejemplo (API): ``{"researcher": tools_ya_arrancadas}`` -> el analista sigue
    recibiendo break_even y run_python.
    """
    if step not in STEPS:
        raise ValueError(f"unknown step {step!r}. Valid: {', '.join(STEPS)}")
    return _build_crew(STEPS[step], llm, tools)


def _build_crew(
    task_names: Sequence[str],
    llm: BaseLLM,
    tools: ToolsByAgent | None = None,
    min_max_iter: int | None = None,
) -> Crew:
    """Crew con las tareas indicadas (en orden) y los agentes que las hacen.

    ``min_max_iter``: si se indica, cada agente tiene al menos esos pasos (se aplica
    al crear el Agent, no después). Lo usa la visión: un paso por foto.
    """
    agents_config, tasks_config = load_config()
    agents: dict[str, Agent] = {}
    tasks: list[Task] = []
    for task_name in task_names:
        task_config = dict(tasks_config[task_name])
        agent_name = task_config.pop("agent")
        if agent_name not in agents:
            if tools is not None and agent_name in tools:
                agent_tools = tools[agent_name]
            else:
                agent_tools = default_tools(agent_name, llm)
            agent_config = dict(agents_config[agent_name])
            if min_max_iter is not None:
                agent_config["max_iter"] = max(agent_config.get("max_iter", 0), min_max_iter)
            agents[agent_name] = Agent(config=agent_config, llm=llm, tools=list(agent_tools))
        if not agents[agent_name].tools:
            task_config["description"] += "\n\n" + NO_TOOLS_NOTE
        tasks.append(Task(config=task_config, agent=agents[agent_name], name=task_name))

    # tracing=False: CrewAI no pregunta ni sube a sus servidores prompts y respuestas
    return Crew(
        agents=list(agents.values()),
        tasks=tasks,
        process=Process.sequential,
        tracing=False,
        verbose=True,
    )


def run_step(step: str, inputs: dict[str, str], llm: BaseLLM, tools: ToolsByAgent | None = None) -> dict[str, str]:
    """Ejecuta un paso y devuelve el texto de cada tarea: {"research_task": "...", ...}.

    ``inputs`` debe venir de ``build_inputs()`` para que no falte ninguna variable.
    """
    if step == "research":
        return _run_research(inputs, llm, tools)
    if step not in STEPS:
        raise ValueError(f"unknown step {step!r}. Valid: {', '.join(STEPS)}")
    return _kickoff(STEPS[step], inputs, llm, tools)


def _kickoff(
    task_names: Sequence[str],
    inputs: dict[str, str],
    llm: BaseLLM,
    tools: ToolsByAgent | None,
    max_iter: int | None = None,
) -> dict[str, str]:
    result = _build_crew(task_names, llm, tools, min_max_iter=max_iter).kickoff(inputs=inputs)
    return {task_name: output.raw for task_name, output in zip(task_names, result.tasks_output, strict=True)}


def _image_count(images: str) -> int:
    """Número de fotos en la variable {images} (una por línea, con viñeta)."""
    if images.strip() == NO_IMAGES:
        return 0
    return sum(1 for line in images.splitlines() if line.strip().startswith("- "))


def _run_research(inputs: dict[str, str], llm: BaseLLM, tools: ToolsByAgent | None) -> dict[str, str]:
    """Paso research: Investigador y Visión son independientes.

    - Sin fotos: la visión no llama al modelo (una llamada menos y menos riesgo de 429).
    - Con fotos: las dos tareas se ejecutan a la vez, en dos hilos; el paso tarda lo
      que tarde la más lenta, no la suma. La visión recibe un paso por foto.
    - Si la visión falla, se devuelve igualmente la investigación (no se pierde trabajo).
    """
    photos = _image_count(inputs.get("images", NO_IMAGES))
    if photos == 0:
        result = _kickoff(("research_task",), inputs, llm, tools)
        return {**result, "vision_task": NO_IMAGES_ANSWER}

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="crew-research") as pool:
        research = pool.submit(_kickoff, ("research_task",), inputs, llm, tools)
        vision = pool.submit(_kickoff, ("vision_task",), inputs, llm, tools, photos + VISION_EXTRA_STEPS)
        # La investigación es imprescindible: si falla, el error sube como antes.
        research_result = research.result()
        # La visión no: si falla, se conserva la investigación y el fallo queda a la vista.
        try:
            vision_result = vision.result()
        except Exception as exc:  # noqa: BLE001 - cualquier fallo de la visión
            logger.warning("Vision task failed, research kept: %s", exc)
            # El detalle técnico solo va al log: la persona usuaria ve un mensaje claro
            vision_result = {"vision_task": VISION_FAILED_ANSWER}
        return {**research_result, **vision_result}


def review_comments(review_text: str) -> list[str]:
    """Traduce la respuesta del Revisor al formato del grafo (``reviewer_comments``).

    Lista vacía = aprobado (el grafo pasa a la aprobación humana).
    Si el Revisor no empieza por "APROBADO", se considera que pide cambios.
    """
    lines = [line.strip() for line in review_text.strip().splitlines() if line.strip()]
    if lines and lines[0].upper().startswith(APPROVED):
        return []
    comments = [line.removeprefix("- ").strip() for line in lines[1:] if line.startswith("- ")]
    return comments or [review_text.strip() or "El revisor no dio una respuesta válida."]
