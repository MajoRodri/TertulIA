"""Construye y ejecuta el crew de TertulIA por pasos.

El grafo (LangGraph, David) decide el orden y el bucle de revisión. Cada nodo del
grafo llama a ``run_step()`` con el nombre de su paso, y el crew ejecuta solo las
tareas de ese paso:

    nodo research  -> run_step("research")  -> research_task + vision_task
    nodo analyst   -> run_step("analysis")  -> analysis_task
    nodo writer    -> run_step("writing")   -> writing_task
    nodo reviewer  -> run_step("review")    -> review_task

No usamos el decorador @CrewBase de CrewAI porque está pensado para ejecutar
todas las tareas de golpe. Aquí construimos a mano un Crew pequeño por paso.

Las herramientas de cada agente salen de agent_tools.py (DEFAULT_TOOLS). Los tests
pasan herramientas falsas con el parámetro ``tools`` para no arrancar servidores.
"""

from collections.abc import Mapping
from pathlib import Path

import yaml
from crewai import LLM, Agent, Crew, Process, Task
from crewai.llms.base_llm import BaseLLM
from crewai.tools import BaseTool

from tertulia.crew.agent_tools import default_tools

# Herramientas por agente: {"researcher": [...], "analyst": [...]}
ToolsByAgent = Mapping[str, list[BaseTool]]

CONFIG_DIR = Path(__file__).resolve().parent / "config"

# Paso del crew -> tareas que ejecuta, en orden
STEPS: dict[str, tuple[str, ...]] = {
    "research": ("research_task", "vision_task"),
    "analysis": ("analysis_task",),
    "writing":  ("writing_task",),
    "review":   ("review_task",),
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
    return LLM(model=f"{provider}/{model_name}", api_key=api_key or None, **extra)


def llm_from_settings() -> LLM:
    """Atajo para el grafo: crea el modelo con los valores de config/settings.py."""
    from config.settings import settings  # se importa aquí: config/ está fuera de src/

    return build_llm(
        settings.LLM_PROVIDER,
        settings.LLM_MODEL_NAME,
        settings.LLM_API_KEY.get_secret_value(),
    )


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

    agents_config, tasks_config = load_config()
    agents: dict[str, Agent] = {}
    tasks: list[Task] = []
    for task_name in STEPS[step]:
        task_config = dict(tasks_config[task_name])
        agent_name = task_config.pop("agent")
        if agent_name not in agents:
            if tools is not None and agent_name in tools:
                agent_tools = tools[agent_name]
            else:
                agent_tools = default_tools(agent_name, llm)
            agents[agent_name] = Agent(
                config=agents_config[agent_name], llm=llm, tools=list(agent_tools)
            )
        if not agents[agent_name].tools:
            task_config["description"] += "\n\n" + NO_TOOLS_NOTE
        tasks.append(Task(config=task_config, agent=agents[agent_name], name=task_name))

    # tracing=False: CrewAI no pregunta ni sube a sus servidores prompts y respuestas
    return Crew(
        agents=list(agents.values()),
        tasks=tasks,
        process=Process.sequential,
        tracing=False,
    )


def run_step(
    step: str, inputs: dict[str, str], llm: BaseLLM, tools: ToolsByAgent | None = None
) -> dict[str, str]:
    """Ejecuta un paso y devuelve el texto de cada tarea: {"research_task": "...", ...}.

    ``inputs`` debe venir de ``build_inputs()`` para que no falte ninguna variable.
    """
    result = build_step_crew(step, llm, tools).kickoff(inputs=inputs)
    return {
        task_name: output.raw
        for task_name, output in zip(STEPS[step], result.tasks_output, strict=True)
    }


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
