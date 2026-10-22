"""Graph nodes for TertulIA."""

from .state import AgentState


def research_node(state: AgentState) -> dict:
    """
    MOCK: Simulates the Researcher agent.
    In the future, this will call the CrewAI agent.
    """
    print("[NODO] Investigador: buscando fuentes...")
    return {"draft_report": "Investigación simulada completada."}


def analyst_node(state: AgentState) -> dict:
    """
    MOCK: Simulates the Analyst agent.
    """
    print("[NODO] Analista: calculando cifras...")
    return {"draft_report": "Análisis simulado completado."}


def writer_node(state: AgentState) -> dict:
    """
    MOCK: Simulates the Writer agent.
    """
    print("[NODO] Redactor: redactando el informe...")
    return {"draft_report": "Borrador de informe simulado."}


def reviewer_node(state: AgentState) -> dict:
    """
    MOCK: Simulates the Reviewer agent.
    For now, it always rejects to test the loop.
    """
    print("[NODO] Revisor: comprobando el informe...")
    return {
        "reviewer_comments": ["Rechazo simulado: faltan fuentes."], 
        "review_round": state.get("review_round", 0) + 1
    }
