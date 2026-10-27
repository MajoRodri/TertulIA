"""Error policy for the TertulIA graph (Issue #14).

Every failure inside the graph is recorded as an ``ErrorEntry`` with a stable
code (``ERR-XXX``) and a severity that decides what the graph does:

- ``DEGRADABLE``: the graph records the error and keeps going with whatever it
  has (empty sources, missing findings, partial report). The human sees it in
  the report and in the verdict warnings.
- ``FATAL``: the graph stops in a controlled way, records the error and goes to
  ``human_approval`` without a verdict. The human decides what to do.

The ``message`` and ``technical_detail`` fields are written in Spanish on
purpose: ``message`` is what the client sees in the report and the UI, and
``technical_detail`` is what we see in the logs. The code, node and severity
stay in English, like the rest of the codebase.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class ErrorSeverity(StrEnum):
    """How bad an error is for the graph."""

    DEGRADABLE = "degradable"
    FATAL = "fatal"


# Stable codes. Keep them in sync with the policy in docs/errores.md.
TOOL_TIMEOUT = "ERR-001"            # external tool did not answer (MCP, API, code_exec)
TOOL_FAILURE = "ERR-002"            # tool answered with an error or invalid arguments
MISSING_DATA = "ERR-003"            # a required figure is not available
LLM_ERROR = "ERR-004"               # the language model failed or answered badly
INVALID_OUTPUT = "ERR-005"          # model output does not fit the schemas
TOKEN_BUDGET_EXHAUSTED = "ERR-006"  # MAX_TOKENS_PER_REPORT reached
MAX_ITERATIONS_REACHED = "ERR-007"  # review loop hit its limit without approval
GRAPH_INTERNAL = "ERR-008"          # unexpected exception inside a node
HUMAN_TIMEOUT = "ERR-009"           # the human did not answer in time


class ErrorEntry(BaseModel):
    """One failure, recorded in the graph state.

    ``node`` is the graph step that produced it (``research``, ``analyst``,
    ``writer``, ``reviewer``, ``human_approval``). ``message`` is shown to the
    client; ``technical_detail`` is for the logs. ``retryable`` is a hint for
    the node: ``True`` means it is worth trying once more before giving up.
    """

    code: str = Field(pattern=r"^ERR-\d{3}$")
    node: str
    severity: ErrorSeverity
    message: str = Field(description="En español: lo que ve el cliente")
    technical_detail: str | None = Field(
        default=None, description="En español: detalle para los logs"
    )
    retryable: bool = False

    def __str__(self) -> str:
        return f"{self.code} [{self.node}] {self.message}"
