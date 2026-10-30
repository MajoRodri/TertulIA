"""Conditional routing logic for the TertulIA graph."""

import logging

from .errors import ErrorSeverity
from .state import AgentState

log = logging.getLogger(__name__)


def should_continue(state: AgentState) -> str:
    """
    Decides whether to loop back to the writer or move forward to the human approval.
    Returns the name of the next node.

    If any error in ``state["errors"]`` is FATAL (for example the token budget,
    ``ERR-006``), the graph stops looping and goes straight to ``human_approval``:
    there is no point reviewing a report that cannot be finished.
    """
    from config.settings import settings  # config/ is outside src/

    max_iterations = settings.MAX_ITERATIONS

    # Fatal errors stop the loop immediately, whatever the review round is.
    fatal_errors = [
        error for error in state.get("errors", [])
        if error.severity == ErrorSeverity.FATAL
    ]
    if fatal_errors:
        log.warning("should_continue: error fatal %s — saltando a human_approval", fatal_errors[0].code)
        return "human_approval"

    review_round = state.get("review_round", 0)
    reviewer_comments = state.get("reviewer_comments", [])

    if reviewer_comments and review_round < max_iterations:
        log.debug("should_continue: ronda %d/%d — volviendo al writer", review_round, max_iterations)
        return "writer"

    log.debug("should_continue: aprobado o límite alcanzado — pasando a human_approval")
    return "human_approval"


def route_after_approval(state: AgentState) -> str:
    """Decide si ir a END o relanzar el writer para aplicar el chat_context."""
    chat_context = state.get("chat_context", "")
    already_applied = state.get("chat_context_applied", False)

    if chat_context and not already_applied:
        log.debug("route_after_approval: aplicando chat_context — volviendo al writer")
        return "writer"

    log.debug("route_after_approval: aprobación final")
    return "human_approval_end"
