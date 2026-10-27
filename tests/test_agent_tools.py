"""Tests de agent_tools.py: qué herramientas tiene cada agente.

No arrancan servidores MCP ni llaman a ningún modelo: las herramientas de Helen se
sustituyen por herramientas falsas con monkeypatch.
"""

import json
import os
import sys
import types

os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

import pytest  # noqa: E402
from crewai.llms.base_llm import BaseLLM  # noqa: E402
from crewai.tools import BaseTool  # noqa: E402

from tertulia.crew import agent_tools  # noqa: E402
from tertulia.crew.agent_tools import (  # noqa: E402
    DEFAULT_TOOLS,
    BreakEvenTool,
    CodeExecTool,
    default_tools,
)
from tertulia.crew.crew import NO_TOOLS_NOTE, STEPS, build_step_crew, load_config  # noqa: E402
from tertulia.crew.inputs import NO_IMAGES, build_inputs  # noqa: E402
from tertulia.crew.sector import list_sectors, load_sector  # noqa: E402
from tertulia.mcp.servers.neighbourhood_data.server import CATEGORY_TAGS  # noqa: E402
from tertulia.schemas import BusinessBrief  # noqa: E402


class FakeLLM(BaseLLM):
    """Modelo falso: no se llama en estos tests, solo hace falta para crear el crew."""

    def call(self, messages, *args, **kwargs):
        return "Thought: listo\nFinal Answer: ok"


class FakeSearch(BaseTool):
    """Sustituye a search_competitors: mismo nombre, sin servidor."""

    name: str = "search_competitors"
    description: str = "Herramienta falsa para tests."

    def _run(self, **kwargs) -> str:
        return "[]"


# --- Tabla de herramientas -------------------------------------------------------


def test_every_agent_has_an_entry():
    agents, _ = load_config()
    assert set(DEFAULT_TOOLS) == set(agents)


def test_writer_and_reviewer_have_no_tools():
    # Solo trabajan con lo que les pasa el grafo: así no pueden traer datos nuevos
    assert default_tools("writer") == []
    assert default_tools("reviewer") == []


def test_analyst_has_break_even_and_code():
    assert {tool.name for tool in default_tools("analyst")} == {"break_even", "run_python"}


def test_unknown_agent_gets_no_tools():
    assert default_tools("marketing") == []


# --- Herramientas del Analista ---------------------------------------------------


def test_break_even_tool_returns_readable_json():
    result = json.loads(
        BreakEvenTool().run(
            business_type="cafe_cowork",
            unit_price=10,
            unit_variable_cost=4,
            fixed_costs=[{"item": "rent", "monthly_amount": 3000}],
        )
    )
    assert result["status"] == "ok" and result["break_even_units_monthly"] == 500


def test_break_even_tool_marks_missing_data_instead_of_inventing():
    result = json.loads(BreakEvenTool().run(business_type="cafe_cowork"))
    assert result["status"] == "missing"
    assert "unit_price" in result["missing_data"]


def test_code_tool_runs_python(tmp_path):
    result = json.loads(CodeExecTool(outputs_root=str(tmp_path)).run(code="print(6 * 7)"))
    assert result["ok"] and result["stdout"].strip() == "42"


# --- Herramientas que vienen de Helen --------------------------------------------


def test_researcher_gets_helens_tools(monkeypatch):
    import tertulia.mcp.client as mcp_client

    monkeypatch.setattr(mcp_client, "researcher_tools", lambda: [FakeSearch()])
    assert [tool.name for tool in default_tools("researcher")] == ["search_competitors"]


def test_researcher_without_mcp_degrades_to_no_tools(monkeypatch):
    import tertulia.mcp.client as mcp_client

    def broken():
        raise FileNotFoundError("uvx not found")

    monkeypatch.setattr(mcp_client, "researcher_tools", broken)
    assert default_tools("researcher") == []  # y crew.py le añadirá NO_TOOLS_NOTE


def test_vision_gets_helens_tool_with_the_crew_model(monkeypatch):
    # Módulo falso con la misma forma que el de Helen (tertulia.vision.tool)
    class AnalyseImageTool(BaseTool):
        name: str = "analyse_image"
        description: str = "Herramienta falsa para tests."
        llm: object = None

        def _run(self, image_path: str) -> str:
            return "sin imágenes"

    fake_module = types.ModuleType("tertulia.vision.tool")
    fake_module.AnalyseImageTool = AnalyseImageTool
    monkeypatch.setitem(sys.modules, "tertulia.vision.tool", fake_module)

    llm = FakeLLM(model="fake")
    (tool,) = default_tools("vision", llm)
    assert tool.name == "analyse_image"
    assert tool.llm is llm  # el mismo modelo que el crew (acordado con Helen)


def test_vision_without_helens_module_has_no_tools(monkeypatch):
    monkeypatch.setitem(sys.modules, "tertulia.vision.tool", None)  # import -> ImportError
    assert agent_tools.vision_tools_if_available() == []


# --- El aviso NO_TOOLS_NOTE solo para quien no tiene herramientas ----------------


def test_note_only_for_agents_without_tools():
    crew = build_step_crew("research", FakeLLM(model="fake"), {"researcher": [FakeSearch()]})
    research, vision = crew.tasks
    assert NO_TOOLS_NOTE not in research.description
    assert NO_TOOLS_NOTE in vision.description


def test_tools_reach_the_agent():
    crew = build_step_crew("analysis", FakeLLM(model="fake"), {"analyst": [BreakEvenTool()]})
    assert [tool.name for tool in crew.agents[0].tools] == ["break_even"]


# --- Contratos con otros módulos -------------------------------------------------


@pytest.mark.parametrize("business_type", list_sectors())
def test_profile_categories_exist_in_helens_server(business_type):
    # Si un perfil pide una categoría que el servidor MCP no conoce, la búsqueda falla
    unknown = set(load_sector(business_type).competitor_categories) - set(CATEGORY_TAGS)
    assert not unknown, f"{business_type}: categorías que el servidor no conoce: {unknown}"


def test_images_come_from_the_brief():
    brief = BusinessBrief(
        business_type="cafe_cowork",
        neighbourhood="Atocha",
        image_paths=["run-001/uploads/fachada.jpg"],
    )
    data = build_inputs(brief, load_sector("cafe_cowork"))
    assert data["images"] == "- run-001/uploads/fachada.jpg"


def test_no_images_in_the_brief():
    brief = BusinessBrief(business_type="cafe_cowork", neighbourhood="Atocha")
    assert build_inputs(brief, load_sector("cafe_cowork"))["images"] == NO_IMAGES


def test_steps_cover_every_agent_with_tools():
    agents_in_steps = {
        load_config()[1][task]["agent"] for tasks in STEPS.values() for task in tasks
    }
    assert agents_in_steps == set(DEFAULT_TOOLS)
