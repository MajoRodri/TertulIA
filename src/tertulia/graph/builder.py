"""Graph assembly and configuration for TertulIA."""

import logging
import os
import sqlite3
from datetime import datetime, timezone

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from tertulia.schemas import TraceEntry

from .edges import route_after_approval, should_continue
from .errors import HUMAN_TIMEOUT, ErrorEntry, ErrorSeverity
from .nodes import analyst_node, research_node, reviewer_node, vision_charts_node, writer_node
from .state import AgentState

log = logging.getLogger(__name__)


def _approval_trace(approved: bool, existing: list[TraceEntry]) -> TraceEntry:
    """TraceEntry for a human approve/reject decision (Issue #13)."""
    return TraceEntry(
        id=f"trc-{len(existing) + 1:03d}",
        timestamp=datetime.now(timezone.utc),
        actor="human",
        tool="ui.approve" if approved else "ui.reject",
        inputs={"human_approved": approved},
        output={"decision": "approved" if approved else "rejected"},
    )


def _timeout_trace(existing: list[TraceEntry]) -> TraceEntry:
    """TraceEntry for a study that expired before the human answered (ERR-009)."""
    return TraceEntry(
        id=f"trc-{len(existing) + 1:03d}",
        timestamp=datetime.now(timezone.utc),
        actor="human",
        tool="ui.timeout",
        inputs={},
        output={"decision": "expired"},
    )


def human_approval_node(state: AgentState) -> dict:
    """
    Registra la decision humana (aprobar, rechazar o caducar) en ``traces``.

    La API escribe ``human_approved`` y ``expired`` en el estado antes de
    reanudar el grafo:

    - ``expired=True``: el estudio caduco sin respuesta humana. Se registra
      ``ERR-009`` en ``errors`` y ``ui.timeout`` en ``traces``. El grafo
      termina con ``human_approved=False``.
    - ``expired=False``: se registra la decision (``ui.approve`` o ``ui.reject``)
      como antes.

    Este nodo NO genera el PDF: eso lo hace la capa API despues de que el grafo
    termine.
    """
    existing_traces = state.get("traces", [])
    existing_errors = state.get("errors", [])

    if state.get("expired", False):
        timeout_error = ErrorEntry(
            code=HUMAN_TIMEOUT,
            node="human_approval",
            severity=ErrorSeverity.FATAL,
            message=(
                "El estudio ha caducado sin respuesta humana. "
                "No se ha generado el informe."
            ),
            technical_detail="El humano no respondio antes de HUMAN_TIMEOUT_S.",
            retryable=False,
        )
        log.warning("human_approval_node: estudio caducado")
        return {
            "human_approved": False,
            "expired": True,
            "traces": existing_traces + [_timeout_trace(existing_traces)],
            "errors": existing_errors + [timeout_error],
        }

    approved = bool(state.get("human_approved", False))
    trace = _approval_trace(approved, existing_traces)
    log.debug("human_approval_node: %s", "aprobado" if approved else "rechazado")
    new_traces = [trace]
    # Procesar competidores descartados por el humano
    discarded = state.get("discarded_competitors", [])
    if discarded:
        log.debug("human_approval_node: %d competidores descartados", len(discarded))
        for i, name in enumerate(discarded):
            new_traces.append(
                TraceEntry(
                    id=f"trc-{len(existing_traces) + i + 2:03d}",
                    timestamp=datetime.now(timezone.utc),
                    actor="human",
                    tool="ui.discard_competitor",
                    inputs={"competitor": name},
                    output={"decision": "discarded"},
                )
            )

    return {
        "human_approved": approved,
        "expired": False,
        "traces": existing_traces + new_traces,
    }


# 1. Inicializamos el grafo con nuestro molde de datos (AgentState)
workflow = StateGraph(AgentState)

# 2. Añadimos los nodos
workflow.add_node("research", research_node)
workflow.add_node("analyst", analyst_node)
workflow.add_node("vision_charts", vision_charts_node)
workflow.add_node("writer", writer_node)
workflow.add_node("reviewer", reviewer_node)
workflow.add_node("human_approval", human_approval_node)

# 3. Conectamos las aristas
workflow.add_edge(START, "research")
workflow.add_edge("research", "analyst")
workflow.add_edge("analyst", "vision_charts")
workflow.add_edge("vision_charts", "writer")
workflow.add_edge("writer", "reviewer")

# 4. Enrutamiento condicional tras el revisor
workflow.add_conditional_edges(
    "reviewer",
    should_continue,
    {
        "writer": "writer",
        "human_approval": "human_approval"
    }
)

# 5. Enrutamiento tras la aprobación humana
workflow.add_conditional_edges(
    "human_approval",
    route_after_approval,
    {
        "writer": "writer",
        "human_approval_end": END
    }
)

# check_same_thread=False: FastAPI accede desde múltiples hilos
# WAL: permite lecturas concurrentes sin bloquear escrituras
_db_path = ":memory:" if os.getenv("TESTING") else "checkpoints.db"
_conn = sqlite3.connect(_db_path, check_same_thread=False)
if _db_path != ":memory:":
    _conn.execute("PRAGMA journal_mode=WAL")
checkpointer = SqliteSaver(_conn)

# 6. Compilamos — interrupt_before pausa el grafo hasta que la API reanude
#    con {"human_approved": True/False} o {"expired": True}.
app = workflow.compile(
    checkpointer=checkpointer,
    interrupt_before=["human_approval"],
)
