from typing import TypedDict, List, Dict, Any

class AgentState(TypedDict):
    """
    Represents the shared state that travels through the LangGraph nodes.
    """
    # 1. The user's request
    request: Dict[str, Any]          
    
    # 2. Data gathered by the Researcher
    sources: List[Dict[str, Any]]    
    
    # 3. Calculations and charts from the Analyst
    analysis_results: Dict[str, Any] 
    
    # 4. The markdown text written by the Writer
    final_report: str                
    
    # 5. Traceability log
    logs: List[str]                  
    
    # 6. Cost control
    tokens_used: int                 
