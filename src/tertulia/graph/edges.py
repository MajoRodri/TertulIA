"""Conditional routing logic for the TertulIA graph."""

from .errors import ErrorSeverity
from .state import AgentState


def should_continue(state: AgentState) -> str:
    """
    Decides whether to loop back to the writer or move forward to the human approval.
    Returns the name of the next node.

    If any error in ``state["errors"]`` is FATAL (for example the token budget,
    ``ERR-006``), the graph stops looping and goes straight to ``human_approval``:
    there is no point reviewing a report that cannot be finished.
    """
    # Límite de iteraciones: viene de config/settings.py (MAX_ITERATIONS = 3).
    from config.settings import settings  # config/ is outside src/

    max_iterations = settings.MAX_ITERATIONS

    # Fatal errors stop the loop immediately, whatever the review round is.
    fatal_errors = [
        error for error in state.get("errors", [])
        if error.severity == ErrorSeverity.FATAL
    ]
    if fatal_errors:
        print(
            f"[FLUJO] Error fatal en el estudio ({fatal_errors[0].code}). "
            "Pasando a aprobación humana sin más revisiones."
        )
        return "human_approval"

    review_round = state.get("review_round", 0)
    reviewer_comments = state.get("reviewer_comments", [])

    # Si hay comentarios (rechazo) y no hemos superado el límite, volvemos al Writer
    if reviewer_comments and review_round < max_iterations:
        print(
            f"[FLUJO] Revisor ha rechazado (Ronda {review_round}/{max_iterations}). "
            "Volviendo al Redactor."
        )
        return "writer"

    # Si no hay comentarios o ya hemos llegado al límite, pasamos a la aprobación humana
    print("[FLUJO] Aprobado o máximo de rondas alcanzado. Pasando a aprobación humana.")
    return "human_approval"
