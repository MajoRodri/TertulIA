"""Graph assembly and configuration for TertulIA."""

from langgraph.graph import StateGraph, START, END
from .state import AgentState
from .nodes import research_node, analyst_node, writer_node, reviewer_node
from .edges import should_continue

def human_approval_node(state: AgentState) -> dict:
    """
    MOCK: Simulates the Human-in-the-loop pause.
    In the final version, LangGraph will pause before this node.
    """
    print("[NODO] Aprobación Humana: Pausa simulada. Generando informe final...")
    return {"human_approved": True}

# 1. Inicializamos el grafo con nuestro molde de datos (AgentState)
workflow = StateGraph(AgentState)

# 2. Añadimos los nodos (las estaciones)
workflow.add_node("research", research_node)
workflow.add_node("analyst", analyst_node)
workflow.add_node("writer", writer_node)
workflow.add_node("reviewer", reviewer_node)
workflow.add_node("human_approval", human_approval_node)

# 3. Conectamos las vías (edges)
workflow.add_edge(START, "research")
workflow.add_edge("research", "analyst")
workflow.add_edge("analyst", "writer")
workflow.add_edge("writer", "reviewer")

# 4. Añadimos la aguja condicional (después del revisor)
workflow.add_conditional_edges(
    "reviewer",
    should_continue,
    {
        "writer": "writer",                  # Si rechaza, vuelve al redactor
        "human_approval": "human_approval"   # Si aprueba, va a la pausa humana
    }
)

# 5. Conectamos la aprobación humana con el final del grafo
workflow.add_edge("human_approval", END)

# 6. Compilamos el grafo para que sea ejecutable
app = workflow.compile()
