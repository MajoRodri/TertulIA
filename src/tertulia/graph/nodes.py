"""Graph nodes for TertulIA.

Issue #14 adds the error policy to the nodes:

- Every node is wrapped in ``try/except``: an unexpected exception becomes an
  ``ERR-008`` entry in ``state["errors"]`` and the node returns a safe partial
  result instead of crashing the graph.
- Before calling the LLM, each node checks the token budget. If it is already
  exhausted, the node does not call the model and records ``ERR-006`` (fatal:
  the graph goes to ``human_approval`` with no verdict).
- Nodes add errors through ``_record_error()``, which returns the state patch
  LangGraph expects (``{"errors": existing + [error]}``).

The nodes are still mocks: the real crew integration is Issue #12. When that
lands, the LLM calls will go inside the same ``try/except`` blocks and the
research node will also use ``capture_tool_events()`` from ``tool_events.py``.
"""

from .errors import (
    GRAPH_INTERNAL,
    TOKEN_BUDGET_EXHAUSTED,
    ErrorEntry,
    ErrorSeverity,
)
from .state import AgentState


def _record_error(state: AgentState, error: ErrorEntry) -> dict:
    """Return a state patch that appends ``error`` to ``state["errors"]``."""
    existing = state.get("errors", [])
    return {"errors": existing + [error]}


def _tokens_exhausted(state: AgentState) -> bool:
    """True if the token budget has already been spent."""
    from config.settings import settings  # config/ is outside src/

    return state.get("tokens_used", 0) >= settings.MAX_TOKENS_PER_REPORT


def _budget_error(node: str) -> ErrorEntry:
    """ERR-006: fatal, the graph stops without a verdict."""
    from config.settings import settings  # config/ is outside src/

    return ErrorEntry(
        code=TOKEN_BUDGET_EXHAUSTED,
        node=node,
        severity=ErrorSeverity.FATAL,
        message=(
            "Se ha agotado el presupuesto de tokens del informe. "
            "El estudio se detiene sin veredicto."
        ),
        technical_detail=f"MAX_TOKENS_PER_REPORT = {settings.MAX_TOKENS_PER_REPORT}",
        retryable=False,
    )


def _internal_error(node: str, exc: BaseException) -> ErrorEntry:
    """ERR-008: an unexpected exception inside a node."""
    return ErrorEntry(
        code=GRAPH_INTERNAL,
        node=node,
        severity=ErrorSeverity.FATAL,
        message=f"Error interno en el nodo {node}. El estudio se detiene.",
        technical_detail=f"{type(exc).__name__}: {exc}",
        retryable=False,
    )


def research_node(state: AgentState) -> dict:
    """
    MOCK: Simulates the Researcher agent.
    In the future, this will call the CrewAI agent (Issue #12) with
    ``capture_tool_events()`` around the call.
    """
    if _tokens_exhausted(state):
        return _record_error(state, _budget_error("research"))

    try:
        print("[NODO] Investigador: buscando fuentes...")
        return {"draft_report": "Investigación simulada completada."}
    except Exception as exc:  # noqa: BLE001 - any failure must not crash the graph
        print(f"[NODO] Investigador: error interno ({exc}).")
        return _record_error(state, _internal_error("research", exc))


def analyst_node(state: AgentState) -> dict:
    """MOCK: Simulates the Analyst agent (Issue #12 will call the real tools)."""
    if _tokens_exhausted(state):
        return _record_error(state, _budget_error("analyst"))

    try:
        print("[NODO] Analista: calculando cifras...")
        return {"draft_report": "Análisis simulado completado."}
    except Exception as exc:  # noqa: BLE001
        print(f"[NODO] Analista: error interno ({exc}).")
        return _record_error(state, _internal_error("analyst", exc))


def writer_node(state: AgentState) -> dict:
    """MOCK: Simulates the Writer agent."""
    if _tokens_exhausted(state):
        return _record_error(state, _budget_error("writer"))

    try:
        print("[NODO] Redactor: redactando el informe...")
        return {"draft_report": "Borrador de informe simulado."}
    except Exception as exc:  # noqa: BLE001
        print(f"[NODO] Redactor: error interno ({exc}).")
        return _record_error(state, _internal_error("writer", exc))


def reviewer_node(state: AgentState) -> dict:
    """MOCK: Simulates the Reviewer agent. Always rejects, to test the loop."""
    if _tokens_exhausted(state):
        return _record_error(state, _budget_error("reviewer"))

    try:
        print("[NODO] Revisor: comprobando el informe...")
        return {
            "reviewer_comments": ["Rechazo simulado: faltan fuentes."],
            "review_round": state.get("review_round", 0) + 1,
        }
    except Exception as exc:  # noqa: BLE001
        print(f"[NODO] Revisor: error interno ({exc}).")
        # A broken reviewer is treated as a rejection, not as an approval.
        patch = _record_error(state, _internal_error("reviewer", exc))
        patch["reviewer_comments"] = [f"Revisor no disponible: {exc}"]
        patch["review_round"] = state.get("review_round", 0) + 1
        return patch
