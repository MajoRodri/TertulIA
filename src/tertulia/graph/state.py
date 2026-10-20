from typing import Any, TypedDict


class AgentState(TypedDict):
    """
    Represents the shared state that travels through the LangGraph nodes.
    """
    # 1. The user's request
    request: dict[str, Any]
    
    # 2. Data gathered by the Researcher
    sources: list[dict[str, Any]]
    
    # 3. Calculations and charts from the Analyst
    analysis_results: dict[str, Any]
    
    # 4. The markdown text written by the Writer
    final_report: str
    
    # 5. Traceability log
    logs: list[str]
    
    # 6. Cost control
    tokens_used: int
