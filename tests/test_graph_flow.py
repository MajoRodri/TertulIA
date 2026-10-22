"""Integration tests for the LangGraph flow."""

from tertulia.graph.builder import app

def test_graph_flow_and_review_limit():
    """
    Tests that the graph correctly flows through the nodes.
    Because the mock Reviewer always rejects, it should loop 3 times
    and then move to human approval.
    """
    initial_state = {
        "request": {},
        "sources": [],
        "findings": [],
        "draft_report": "",
        "review_round": 0,
        "reviewer_comments": [],
        "verdict": None,
        "traces": [],
        "tokens_used": 0,
        "human_approved": False,
        "errors": []
    }

    # Ejecutamos el grafo
    final_state = app.invoke(initial_state)

    # Comprobaciones (Assertions)
    # 1. El revisor debió rechazar 3 veces, así que la ronda final debe ser 3.
    assert final_state["review_round"] == 3
    
    # 2. Al llegar a la ronda 3, el grafo debe pasar a aprobación humana.
    assert final_state["human_approved"] is True
    
    # 3. El borrador del informe debe ser el texto simulado.
    assert "Borrador de informe simulado" in final_state["draft_report"]
