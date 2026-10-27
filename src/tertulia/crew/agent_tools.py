"""Qué herramientas tiene cada agente del crew (mínimo privilegio).

Cada módulo decide QUÉ herramientas existen; este archivo decide QUIÉN las usa:

    researcher  -> researcher_tools() de Helen (search_competitors + fetch, por MCP)
    analyst     -> punto de equilibrio y ejecución de código de Yohanna
    vision      -> AnalyseImageTool de Helen (#32), en cuanto esté en dev (ver abajo)
    writer      -> ninguna: solo trabaja con los resultados que le pasa el grafo
    reviewer    -> ninguna: solo compara el borrador con esos resultados

Si un agente se queda sin herramientas, crew.py le añade el aviso NO_TOOLS_NOTE,
así que nunca se le pide buscar datos que no puede conseguir.
"""

import json
import logging
from collections.abc import Callable
from typing import Any

from crewai.llms.base_llm import BaseLLM
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from tertulia.tools.code_exec import run_code_tool
from tertulia.tools.punto_equilibrio import BreakEvenInput, break_even_tool

logger = logging.getLogger(__name__)


def _as_text(result: dict[str, Any]) -> str:
    """El agente lee texto: JSON legible, con tildes, para que lo cite tal cual."""
    return json.dumps(result, ensure_ascii=False, default=str)


# --- Herramientas del Analista (envoltorio fino del código de Yohanna) -----------


class BreakEvenTool(BaseTool):
    """Punto de equilibrio: envuelve break_even_tool() sin cambiar su lógica."""

    name: str = "break_even"
    description: str = (
        "Calcula el punto de equilibrio mensual de un negocio. Recibe el precio por "
        "unidad, el coste variable por unidad y la lista de costes fijos mensuales "
        "(item y monthly_amount). Si un dato no se conoce, déjalo vacío: la herramienta "
        "lo marca como 'missing' y nunca lo inventa."
    )
    args_schema: type[BaseModel] = BreakEvenInput

    def _run(self, **kwargs: Any) -> str:
        return _as_text(break_even_tool(**kwargs))


class _CodeArgs(BaseModel):
    code: str = Field(
        description=(
            "Script de Python con pandas (pd) y matplotlib (plt). Guarda los gráficos "
            "en la carpeta OUTPUT, por ejemplo plt.savefig(f'{OUTPUT}/grafico.png')."
        )
    )


class CodeExecTool(BaseTool):
    """Ejecución de código: envuelve run_code_tool() (proceso aparte, sin claves)."""

    name: str = "run_python"
    description: str = (
        "Ejecuta un script de Python para analizar datos o generar un gráfico. "
        "Devuelve la salida, los errores y las rutas de los archivos generados."
    )
    args_schema: type[BaseModel] = _CodeArgs
    outputs_root: str = "outputs"

    def _run(self, code: str) -> str:
        return _as_text(run_code_tool(code, outputs_root=self.outputs_root))


def analyst_tools(llm: BaseLLM | None = None) -> list[BaseTool]:
    return [BreakEvenTool(), CodeExecTool()]


# --- Herramientas que vienen de otros módulos ------------------------------------


def researcher_tools_or_none(llm: BaseLLM | None = None) -> list[BaseTool]:
    """Herramientas MCP de Helen. Si no arrancan (p. ej. falta uvx), el agente sigue
    sin herramientas y responde «sin dato»: mejor un dato que falta que uno inventado.
    """
    try:
        from tertulia.mcp.client import researcher_tools

        return researcher_tools()
    except Exception as exc:  # noqa: BLE001 - cualquier fallo al arrancar los servidores
        logger.warning("Researcher without tools: MCP tools failed to start (%s)", exc)
        return []


def vision_tools_if_available(llm: BaseLLM | None = None) -> list[BaseTool]:
    """Herramienta de visión de Helen (#32): ``AnalyseImageTool`` en ``tertulia.vision.tool``.

    Recibe el MISMO modelo que el crew, para que la visión use el mismo proveedor
    (acordado con Helen). Mientras su módulo no esté en dev, el agente de visión no
    tiene herramientas y responde «sin imágenes».
    """
    try:
        from tertulia.vision.tool import AnalyseImageTool
    except ImportError:
        return []
    return [AnalyseImageTool(llm=llm)]


def no_tools(llm: BaseLLM | None = None) -> list[BaseTool]:
    return []


# Agente -> función que crea sus herramientas (se llama solo cuando hace falta).
# Todas reciben el modelo del crew, aunque solo la de visión lo usa.
DEFAULT_TOOLS: dict[str, Callable[[BaseLLM | None], list[BaseTool]]] = {
    "researcher": researcher_tools_or_none,
    "analyst": analyst_tools,
    "vision": vision_tools_if_available,
    "writer": no_tools,
    "reviewer": no_tools,
}


def default_tools(agent_name: str, llm: BaseLLM | None = None) -> list[BaseTool]:
    """Herramientas de un agente. Un agente que no está en la tabla no recibe ninguna."""
    return DEFAULT_TOOLS.get(agent_name, no_tools)(llm)
