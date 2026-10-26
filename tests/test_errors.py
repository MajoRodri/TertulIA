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
    assert patch_ == {"draft_report": "Investigación simulada completada."}


# --- ERR-008: unexpected exception inside a node -----------------------------


def test_research_node_catches_unexpected_exceptions():
    # Only the first print fails: the except branch also prints, and that one must work.
    with patch("builtins.print", side_effect=[RuntimeError("boom"), None]):
        patch_ = research_node(_state())
    assert len(patch_["errors"]) == 1
    error = patch_["errors"][0]
    assert error.code == GRAPH_INTERNAL
    assert error.node == "research"
    assert error.severity == ErrorSeverity.FATAL
    assert "boom" in (error.technical_detail or "")


def test_reviewer_failure_is_treated_as_rejection():
    with patch("builtins.print", side_effect=[RuntimeError("reviewer down"), None]):
        patch_ = reviewer_node(_state(review_round=1))
    assert patch_["errors"][0].code == GRAPH_INTERNAL
    assert patch_["review_round"] == 2
    assert patch_["reviewer_comments"]
    assert "reviewer down" in patch_["reviewer_comments"][0]


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
