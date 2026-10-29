from typing import TypedDict

from tertulia.schemas import BusinessBrief, Finding, Source, TraceEntry, Verdict

from .errors import ErrorEntry


class AgentState(TypedDict):
    """
    Represents the shared state that travels through the LangGraph nodes.
    Using strict Pydantic models for data integrity and traceability.
    """
    # 1. The user's request (Km. 0)
    request: BusinessBrief

    # 2. Data gathered by the Researcher (La Portera)
    sources: list[Source]

    # 3. Calculations and charts from the Analyst (Chulapo Analytics)
    findings: list[Finding]

    # 4. The markdown text written by the Writer
    draft_report: str

    # 5. Review loop control
    review_round: int
    reviewer_comments: list[str]

    # 6. The final verdict (¿Mola?)
    verdict: Verdict | None

    # 7. Traceability and cost control (David's domain)
    traces: list[TraceEntry]
    tokens_used: int

    # 8. Graph status and Human-in-the-loop
    human_approved: bool
    expired: bool  # True when the API reanuda a paused study past HUMAN_TIMEOUT_S
    errors: list[ErrorEntry]

    # 9. Raw text from each crew task (Issue #12). The nodes call run_step()
    #    and store the text here; the parser turns it into sources/findings.
    research_result: str
    vision_result: str
    analysis_result: str

    # 10. Contexto del chat (Issue #12). Se inyecta antes de reanudar.
    chat_context: str
    chat_context_applied: bool

    # 11. Resumen de texto generado por el adapter MCP (Issue #12).
    mcp_research_summary: str

    # 12. Competidores descartados por el humano (Issue #12).
    discarded_competitors: list[str]
