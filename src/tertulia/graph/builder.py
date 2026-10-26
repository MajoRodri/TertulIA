"""Graph assembly and configuration for TertulIA."""

from datetime import datetime, timezone

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from tertulia.schemas import TraceEntry

from .edges import should_continue
from .nodes import analyst_node, research_node, reviewer_node, writer_node
from .state import AgentState


def human_approval_node(state: AgentState) -> dict:
    """
    Registra la decision humana (aprobar o rechazar) como un TraceEntry.

    La decision llega en ``state["human_approved"]``: la API la escribe antes de
    reanudar el grafo. Este nodo NO genera el PDF (eso lo hace la capa API despues
    de que el grafo termine). Aqui solo se registra la decision humana.
    """
    approved = bool(state.get("human_approved", False))
    existing = state.get("traces", [])
    next_id = f"trc-{len(existing) + 1:03d}"

    trace = TraceEntry(
        id=next_id,
        timestamp=datetime.now(timezone.utc),
        actor="human",
        tool="ui.approve" if approved else "ui.reject",
        inputs={"human_approved": approved},
        output={"decision": "approved" if approved else "rejected"},
    )

    if approved:
        print("[NODO] Aprobacion humana: informe aprobado.")
    else:
        print("[NODO] Aprobacion humana: informe rechazado.")

    return {"human_approved": approved, "traces": existing + [trace]}


# 1. Inicializamos el grafo con nuestro molde de datos (AgentState)
workflow = StateGraph(AgentState)

# 2. Anadimos los nodos (las estaciones)
workflow.add_node("research", research_node)
workflow.add_node("analyst", analyst_node)
workflow.add_node("writer", writer_node)
workflow.add_node("reviewer", reviewer_node)
workflow.add_node("human_approval", human_approval_node)

# 3. Conectamos las vias (edges)
workflow.add_edge(START, "research")
workflow.add_edge("research", "analyst")
workflow.add_edge("analyst", "writer")
workflow.add_edge("writer", "reviewer")

# 4. Anadimos la aguja condicional (despues del revisor)
workflow.add_conditional_edges(
    "reviewer",
    should_continue,
    {
        "writer": "writer",
        "human_approval": "human_approval"
    }
)

# 5. Conectamos la aprobacion humana con el final del grafo
workflow.add_edge("human_approval", END)

# 6. Compilamos el grafo con checkpointer y pausa antes de la aprobacion humana.
#    MemorySaver guarda el estado en memoria del proceso (suficiente para la demo:
#    FastAPI y el grafo corren en el mismo proceso). Upgrade post-demo: SqliteSaver.
#    interrupt_before=["human_approval"] hace que el grafo se pare justo antes de
#    ese nodo, esperando a que la API lo reanude con {"human_approved": True/False}.
app = workflow.compile(
    checkpointer=MemorySaver(),
    interrupt_before=["human_approval"],
)
