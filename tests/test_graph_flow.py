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
