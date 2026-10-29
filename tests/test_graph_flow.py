"""Integration tests for the LangGraph flow."""

from tertulia.graph.builder import app

INITIAL_STATE = {
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
    "errors": [],
    "research_result": "",
    "vision_result": "",
    "analysis_result": "",
}


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def test_graph_pauses_before_human_approval():
    """
    The mock reviewer always rejects, so the graph loops 3 times and then
    pauses before human_approval (human-in-the-loop).
    """
    config = _config("test-pause")
    app.invoke(INITIAL_STATE, config)

    state = app.get_state(config)
    assert state.values["review_round"] == 3
    assert state.values["human_approved"] is False
    assert state.next == ("human_approval",)


def test_approval_resumes_graph_and_logs_approve_trace():
    """update_state + invoke(None) resumes and logs ui.approve."""
    config = _config("test-approve")
    app.invoke(INITIAL_STATE, config)
    app.update_state(config, {"human_approved": True})
    final = app.invoke(None, config)

    assert final["human_approved"] is True
    traces = final["traces"]
    assert len(traces) == 1
    assert traces[0].actor == "human"
    assert traces[0].tool == "ui.approve"
    assert traces[0].inputs == {"human_approved": True}


def test_rejection_resumes_graph_and_logs_reject_trace():
    """update_state + invoke(None) resumes and logs ui.reject."""
    config = _config("test-reject")
    app.invoke(INITIAL_STATE, config)
    app.update_state(config, {"human_approved": False})
    final = app.invoke(None, config)

    assert final["human_approved"] is False
    traces = final["traces"]
    assert len(traces) == 1
    assert traces[0].actor == "human"
    assert traces[0].tool == "ui.reject"
    assert traces[0].inputs == {"human_approved": False}

def test_graph_pauses_twice_and_applies_chat_context():
    """
    Simula el flujo real: pausa 1 -> inyecta chat_context -> pausa 2 -> termina.
    """
    config = _config("test-chat-context")
    app.invoke(INITIAL_STATE, config)

    # 1. Primera pausa
    assert app.get_state(config).next == ("human_approval",)

    # 2. Reanudamos inyectando el chat_context
    app.update_state(config, {
        "human_approved": True,
        "chat_context": "Tengo un local de 120 m2"
    })
    app.invoke(None, config)

    # 3. Debería haber vuelto al writer, aplicado el flag, y pausado otra vez
    state = app.get_state(config)
    assert state.next == ("human_approval",)
    assert state.values["chat_context_applied"] is True

    # 4. Aprobación final
    app.update_state(config, {"human_approved": True})
    final = app.invoke(None, config)

    # 5. Fin
    assert app.get_state(config).next == ()
    assert final["human_approved"] is True
