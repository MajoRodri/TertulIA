"""Conditional routing logic for the TertulIA graph."""

from .state import AgentState


def should_continue(state: AgentState) -> str:
    """
    Decides whether to loop back to the writer or move forward to the human approval.
    Returns the name of the next node.
    """
    # Límite de iteraciones: viene de config/settings.py (MAX_ITERATIONS = 3).
    from config.settings import settings  # config/ is outside src/

    max_iterations = settings.MAX_ITERATIONS

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
