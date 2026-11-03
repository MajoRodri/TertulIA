"""Tests for the error policy in the graph nodes (Issue #14)."""

from unittest.mock import patch

from tertulia.graph.errors import (
    GRAPH_INTERNAL,
    TOKEN_BUDGET_EXHAUSTED,
    ErrorSeverity,
)
from tertulia.graph.nodes import (
    analyst_node,
    research_node,
    reviewer_node,
    writer_node,
)


def _state(**overrides):
    state = {
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
    state.update(overrides)
    return state


# --- ERR-006: token budget exhausted -----------------------------------------


def test_research_node_stops_when_tokens_are_exhausted():
    with patch("config.settings.settings.MAX_TOKENS_PER_REPORT", 100):
        patch_ = research_node(_state(tokens_used=100))
    assert "errors" in patch_
    assert len(patch_["errors"]) == 1
    error = patch_["errors"][0]
    assert error.code == TOKEN_BUDGET_EXHAUSTED
    assert error.node == "research"
    assert error.severity == ErrorSeverity.FATAL


def test_analyst_writer_and_reviewer_also_check_tokens():
    for node_fn, name in [
        (analyst_node, "analyst"),
        (writer_node, "writer"),
        (reviewer_node, "reviewer"),
    ]:
        with patch("config.settings.settings.MAX_TOKENS_PER_REPORT", 100):
            patch_ = node_fn(_state(tokens_used=100))
        assert patch_["errors"][0].code == TOKEN_BUDGET_EXHAUSTED
        assert patch_["errors"][0].node == name


def test_node_does_not_stop_below_the_budget():
    with patch("config.settings.settings.MAX_TOKENS_PER_REPORT", 1000):
        patch_ = research_node(_state(tokens_used=500))
    assert patch_ == {}


# --- ERR-008: unexpected exception inside a node -----------------------------


def test_research_node_returns_empty_patch_when_below_budget():
    with patch("config.settings.settings.MAX_TOKENS_PER_REPORT", 1000):
        patch_ = research_node(_state(tokens_used=0))
    assert patch_ == {}


def test_reviewer_failure_is_treated_as_rejection():
    # crewai is not installed in the test environment, so the import inside
    # reviewer_node raises ModuleNotFoundError — that's caught as a runtime
    # failure and treated as a rejection, exactly like any other exception.
    patch_ = reviewer_node(_state(review_round=1))
    assert patch_["errors"][0].code == GRAPH_INTERNAL
    assert patch_["review_round"] == 2
    assert patch_["reviewer_comments"]


# --- The errors list keeps growing, it does not overwrite --------------------


def test_new_errors_are_appended_to_existing_ones():
    from tertulia.graph.errors import ErrorEntry

    previous = ErrorEntry(
        code=GRAPH_INTERNAL,
        node="research",
        severity=ErrorSeverity.DEGRADABLE,
        message="anterior",
    )
    with patch("config.settings.settings.MAX_TOKENS_PER_REPORT", 100):
        patch_ = research_node(_state(tokens_used=100, errors=[previous]))
    assert len(patch_["errors"]) == 2
    assert patch_["errors"][0] is previous
    assert patch_["errors"][1].code == TOKEN_BUDGET_EXHAUSTED


# --- FATAL errors stop the review loop in should_continue --------------------


def test_should_continue_goes_to_human_approval_on_fatal_error():
    from tertulia.graph.edges import should_continue
    from tertulia.graph.errors import TOKEN_BUDGET_EXHAUSTED, ErrorEntry

    fatal = ErrorEntry(
        code=TOKEN_BUDGET_EXHAUSTED,
        node="research",
        severity=ErrorSeverity.FATAL,
        message="presupuesto agotado",
    )
    state = _state(
        reviewer_comments=["Rechazo simulado: faltan fuentes."],
        review_round=1,
        errors=[fatal],
    )
    assert should_continue(state) == "human_approval"


def test_should_continue_keeps_looping_with_degradable_errors():
    from tertulia.graph.edges import should_continue
    from tertulia.graph.errors import TOOL_FAILURE, ErrorEntry

    degradable = ErrorEntry(
        code=TOOL_FAILURE,
        node="research",
        severity=ErrorSeverity.DEGRADABLE,
        message="herramienta caída",
    )
    state = _state(
        reviewer_comments=["Rechazo simulado: faltan fuentes."],
        review_round=1,
        errors=[degradable],
    )
    assert should_continue(state) == "writer"


# --- ERR-009: a paused study that expires without a human decision -----------


def test_human_approval_records_timeout_error_and_trace():
    from tertulia.graph.builder import app

    config = {"configurable": {"thread_id": "test-expired"}}
    app.invoke(_state(), config)

    # Resume as the API would when the study has expired.
    app.update_state(config, {"expired": True})
    final = app.invoke(None, config)

    assert final["human_approved"] is False
    assert final["expired"] is True
    # The reviewer also fails in tests (request is a plain dict, not a Brief),
    # so there may be an ERR-008 too — we only assert the timeout error is present.
    timeout_errors = [e for e in final["errors"] if e.code == "ERR-009"]
    assert len(timeout_errors) == 1
    error = timeout_errors[0]
    assert error.node == "human_approval"
    assert error.severity == ErrorSeverity.FATAL

    timeout_traces = [t for t in final["traces"] if t.tool == "ui.timeout"]
    assert len(timeout_traces) == 1
    trace = timeout_traces[0]
    assert trace.actor == "human"
    assert trace.output == {"decision": "expired"}


def test_human_approval_does_not_record_timeout_when_not_expired():
    from tertulia.graph.builder import app

    config = {"configurable": {"thread_id": "test-not-expired"}}
    app.invoke(_state(), config)
    app.update_state(config, {"human_approved": True, "expired": False})
    final = app.invoke(None, config)

    # No timeout error — reviewer may still fail with ERR-008 in test env.
    assert not any(e.code == "ERR-009" for e in final["errors"])
    assert final["traces"][0].tool == "ui.approve"
