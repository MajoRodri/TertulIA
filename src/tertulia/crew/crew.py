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

Las herramientas (punto de equilibrio, código, MCP, visión) se asignarán a cada
agente en la siguiente entrega (#20, 30 oct).
"""

from pathlib import Path

import yaml
from crewai import LLM, Agent, Crew, Process, Task
from crewai.llms.base_llm import BaseLLM

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


def build_llm(provider: str, model_name: str, api_key: str | None = None) -> LLM:
    """Crea el modelo de lenguaje. No hace ninguna llamada: solo lo configura.

    Los valores vienen de config/settings.py (David), p. ej. ``"gemini"`` y
    ``"gemini-3.8-flash"``. Cambiar de modelo no obliga a tocar este archivo.
    """
    return LLM(model=f"{provider}/{model_name}", api_key=api_key or None)


def llm_from_settings() -> LLM:
    """Atajo para el grafo: crea el modelo con los valores de config/settings.py."""
    from config.settings import settings  # se importa aquí: config/ está fuera de src/

    return build_llm(
        settings.LLM_PROVIDER,
        settings.LLM_MODEL_NAME,
        settings.LLM_API_KEY.get_secret_value(),
    )


def build_step_crew(step: str, llm: BaseLLM) -> Crew:
    """Crew con solo las tareas de ``step`` y los agentes que las hacen."""
    if step not in STEPS:
        raise ValueError(f"unknown step {step!r}. Valid: {', '.join(STEPS)}")

    agents_config, tasks_config = load_config()
    agents: dict[str, Agent] = {}
    tasks: list[Task] = []
    for task_name in STEPS[step]:
        task_config = dict(tasks_config[task_name])
        agent_name = task_config.pop("agent")
        if agent_name not in agents:
            agents[agent_name] = Agent(config=agents_config[agent_name], llm=llm)
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


def run_step(step: str, inputs: dict[str, str], llm: BaseLLM) -> dict[str, str]:
    """Ejecuta un paso y devuelve el texto de cada tarea: {"research_task": "...", ...}.

    ``inputs`` debe venir de ``build_inputs()`` para que no falte ninguna variable.
    """
    result = build_step_crew(step, llm).kickoff(inputs=inputs)
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
