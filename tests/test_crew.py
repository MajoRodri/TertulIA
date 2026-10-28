"""Tests de crew.py e inputs.py.

Usan un modelo FALSO (FakeLLM) que responde siempre lo mismo: comprueban que el crew
se construye y se ejecuta bien sin internet, sin claves y sin gastar tokens.
Que el modelo real responda bien se prueba aparte, a mano, con una clave.
"""

import os
import time

os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

import pytest  # noqa: E402
from crewai.llms.base_llm import BaseLLM  # noqa: E402

from tertulia.crew.crew import (  # noqa: E402
    LLM_RETRY_ATTEMPTS,
    LLM_TIMEOUT_S,
    NO_IMAGES_ANSWER,
    NO_TOOLS_NOTE,
    STEPS,
    build_llm,
    build_step_crew,
    review_comments,
    run_step,
)
from tertulia.crew.inputs import (  # noqa: E402
    FIRST_DRAFT,
    NO_DATA,
    NO_IMAGES,
    TASK_INPUT_KEYS,
    build_inputs,
)
from tertulia.crew.sector import load_sector  # noqa: E402
from tertulia.schemas import BusinessBrief  # noqa: E402

# Los tests nunca usan las herramientas reales: arrancarían servidores MCP.
# Un agente que no está en el diccionario recibiría sus herramientas por defecto,
# así que se deja a TODOS sin herramientas de forma explícita.
NO_TOOLS: dict = {agent: [] for agent in ("researcher", "vision", "analyst", "writer", "reviewer")}


class FakeLLM(BaseLLM):
    """Modelo de prueba: guarda lo que recibe y responde siempre lo mismo."""

    answer: str = "respuesta de prueba"
    received: list = []

    def call(self, messages, *args, **kwargs):
        self.received.append(str(messages))
        return f"Thought: listo\nFinal Answer: {self.answer}"

    def supports_function_calling(self) -> bool:
        return False


@pytest.fixture
def brief():
    return BusinessBrief(business_type="cafe_cowork", neighbourhood="Atocha")


@pytest.fixture
def inputs(brief):
    return build_inputs(brief, load_sector("cafe_cowork"))


# --- build_inputs ---------------------------------------------------------------


def test_inputs_have_exactly_the_contract_keys(inputs):
    assert set(inputs) == TASK_INPUT_KEYS


def test_no_input_is_empty(inputs):
    # Apunte de David: en la primera ronda tienen que viajar con un texto por defecto
    assert all(isinstance(v, str) and v.strip() for v in inputs.values())


def test_first_round_defaults(inputs):
    assert inputs["review_feedback"] == FIRST_DRAFT
    assert inputs["images"] == NO_IMAGES
    assert inputs["budget"] == NO_DATA  # no se inventa un presupuesto


def test_lists_are_readable_text(brief):
    data = build_inputs(
        brief.model_copy(update={"budget_eur": 30000}),
        load_sector("cafe_cowork"),
        review_feedback=["Falta la fuente del alquiler"],
    )
    assert data["competitor_categories"] == "cafe, coworking"
    assert "- Alquiler del local" in data["fixed_cost_items"]
    assert data["review_feedback"] == "- Falta la fuente del alquiler"
    assert data["budget"] == "30000 EUR"


# --- Construcción del crew ------------------------------------------------------


@pytest.mark.parametrize("step", sorted(STEPS))
def test_each_step_builds_its_tasks(step):
    crew = build_step_crew(step, FakeLLM(model="fake"), NO_TOOLS)
    assert [task.name for task in crew.tasks] == list(STEPS[step])


def test_unknown_step_is_rejected():
    with pytest.raises(ValueError, match="unknown step"):
        build_step_crew("marketing", FakeLLM(model="fake"), NO_TOOLS)


def test_tracing_is_disabled():
    # Privacidad: CrewAI no debe subir prompts ni respuestas a sus servidores
    assert build_step_crew("research", FakeLLM(model="fake"), NO_TOOLS).tracing is False


def test_agents_without_tools_are_told_so():
    # Prueba real del 23 oct: sin este aviso, el Investigador inventó cifras y enlaces
    crew = build_step_crew("research", FakeLLM(model="fake"), NO_TOOLS)
    assert all(NO_TOOLS_NOTE in task.description for task in crew.tasks)


def test_no_tools_note_reaches_the_model(inputs):
    llm = FakeLLM(model="fake", received=[])
    run_step("research", inputs, llm, NO_TOOLS)
    assert "NO tienes ninguna herramienta" in llm.received[0]


def test_gemini_retries_and_timeout_reach_the_client():
    # Sin esto, un 429 de la capa gratuita falla al primer intento (comprobado)
    llm = build_llm("gemini", "gemini-3.5-flash-lite", api_key="clave-falsa")
    options = llm._get_sync_client()._api_client._http_options
    assert options.timeout == LLM_TIMEOUT_S * 1000
    assert options.retry_options.attempts == LLM_RETRY_ATTEMPTS


def test_other_providers_get_no_gemini_options():
    assert not getattr(build_llm("openai", "gpt-x", api_key="clave-falsa"), "client_params", None)


def test_build_llm_does_not_call_the_api():
    llm = build_llm("gemini", "gemini-3.8-flash", api_key="clave-falsa")
    assert llm.model == "gemini-3.8-flash"


# --- Ejecución con el modelo falso ----------------------------------------------


def test_research_without_photos_skips_the_vision_call(inputs):
    # Sin fotos, la visión no llama al modelo: una llamada menos (y menos 429)
    llm = FakeLLM(model="fake", received=[])
    result = run_step("research", inputs, llm, NO_TOOLS)
    assert result == {"research_task": "respuesta de prueba", "vision_task": NO_IMAGES_ANSWER}
    assert len(llm.received) == 1  # solo el Investigador
    assert "Atocha" in llm.received[0]  # las variables llegaron al agente


def test_research_with_photos_runs_both_tasks_in_parallel(brief):
    class SlowLLM(FakeLLM):
        def call(self, messages, *args, **kwargs):
            time.sleep(1.5)
            return super().call(messages, *args, **kwargs)

    data = build_inputs(brief, load_sector("cafe_cowork"), images=["run-1/a.jpg", "run-1/b.jpg"])
    llm = SlowLLM(model="fake", received=[])
    start = time.monotonic()
    result = run_step("research", data, llm, NO_TOOLS)
    elapsed = time.monotonic() - start
    assert result == {"research_task": "respuesta de prueba", "vision_task": "respuesta de prueba"}
    assert len(llm.received) == 2
    assert elapsed < 2.8  # en serie serían más de 3 s (1,5 s por llamada)


def test_vision_gets_one_step_per_photo():
    # Con max_iter=5 solo se analizaban 5 de 10 fotos (comprobado con CrewAI 1.15.28)
    from crewai.tools import BaseTool

    analysed: list[str] = []

    class Photo(BaseTool):
        name: str = "analyse_image"
        description: str = "Herramienta falsa para tests."

        def _run(self, image_path: str) -> str:
            analysed.append(image_path)
            return "foto analizada"

    class OnePhotoPerStep(FakeLLM):
        # El Investigador corre a la vez en otro hilo: solo se cuentan las llamadas
        # del agente de visión, para que el resultado no dependa del orden de los hilos.
        def call(self, messages, *args, **kwargs):
            if "Analista visual" not in str(messages):
                return "Thought: listo\nFinal Answer: hecho"
            self.received.append(str(messages))
            n = len(self.received)
            if n <= 10:
                return f'Thought: siguiente\nAction: analyse_image\nAction Input: {{"image_path": "f{n}.jpg"}}'
            return "Thought: listo\nFinal Answer: hecho"

    photos = [f"run-1/f{i}.jpg" for i in range(1, 11)]
    data = build_inputs(
        BusinessBrief(business_type="cafe_cowork", neighbourhood="Atocha"), load_sector("cafe_cowork"), images=photos
    )
    tools = {**NO_TOOLS, "vision": [Photo()]}
    run_step("research", data, OnePhotoPerStep(model="fake", received=[]), tools)
    assert len(set(analysed)) == 10


def test_writer_receives_previous_results(brief):
    data = build_inputs(
        brief,
        load_sector("cafe_cowork"),
        research_result="Hay 4 cafeterías en Atocha",
        review_feedback=["Cita la fuente"],
    )
    llm = FakeLLM(model="fake", received=[])
    run_step("writing", data, llm, NO_TOOLS)
    assert "Hay 4 cafeterías en Atocha" in llm.received[0]
    assert "Cita la fuente" in llm.received[0]


# --- Respuesta del revisor ------------------------------------------------------


def test_approved_review_has_no_comments():
    assert review_comments("APROBADO\nTodo correcto.") == []


def test_rejected_review_returns_each_problem():
    text = "CAMBIOS NECESARIOS\n- Falta la fuente del alquiler\n- El semáforo no se justifica"
    assert review_comments(text) == [
        "Falta la fuente del alquiler",
        "El semáforo no se justifica",
    ]


def test_unexpected_review_counts_as_changes():
    assert review_comments("No sé qué decir") == ["No sé qué decir"]
