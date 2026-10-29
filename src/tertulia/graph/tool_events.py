"""Map CrewAI tool events to ErrorEntry objects (Issue #14).

CrewAI emits events when a tool fails. We listen to three of them:

- ``MCPToolExecutionFailedEvent``: the MCP client got an error from a server.
  The error text carries our semantic code (``[invalid_input]``,
  ``[not_found]``, ``[source_unavailable]``) somewhere inside it, because MCP
  adds a prefix. ``error_code()`` from ``tertulia.mcp.client`` finds it.
- ``ToolValidateInputErrorEvent``: CrewAI rejected the tool arguments against
  its schema before calling the tool. The MCP listener never sees these.
- ``ToolUsageErrorEvent``: a tool raised an exception (not MCP).

The converter functions below take an event and return an ``ErrorEntry``
(or ``None`` when the event does not map to an error). The node that calls the
crew registers listeners with ``crewai_event_bus.scoped_handlers()``, collects
the errors and adds them to ``state["errors"]``.
"""

from crewai.events.types.mcp_events import MCPToolExecutionFailedEvent
from crewai.events.types.tool_usage_events import (
    ToolUsageErrorEvent,
    ToolValidateInputErrorEvent,
)

from tertulia.mcp.client import error_code

from .errors import (
    MISSING_DATA,
    TOOL_FAILURE,
    TOOL_TIMEOUT,
    ErrorEntry,
    ErrorSeverity,
)


def _mcp_event_to_error(event: MCPToolExecutionFailedEvent) -> ErrorEntry | None:
    """Map an MCP failure to an ErrorEntry, or None if it is not an error we track."""
    semantic = error_code(event.error)

    if semantic == "not_found":
        return ErrorEntry(
            code=MISSING_DATA,
            node="research",
            severity=ErrorSeverity.DEGRADABLE,
            message=(
                f"No se encontraron datos para {event.tool_args.get('neighbourhood', 'el barrio')}."
            ),
            technical_detail=event.error,
            retryable=False,
        )

    if semantic == "invalid_input":
        return ErrorEntry(
            code=TOOL_FAILURE,
            node="research",
            severity=ErrorSeverity.DEGRADABLE,
            message="Los argumentos de la búsqueda no son válidos.",
            technical_detail=event.error,
            retryable=False,
        )

    if semantic == "source_unavailable" or event.error_type == "timeout":
        return ErrorEntry(
            code=TOOL_TIMEOUT,
            node="research",
            severity=ErrorSeverity.DEGRADABLE,
            message=(
                "La fuente de datos no responde. Se usan datos guardados si están disponibles."
            ),
            technical_detail=event.error,
            retryable=True,
        )

    return ErrorEntry(
        code=TOOL_FAILURE,
        node="research",
        severity=ErrorSeverity.DEGRADABLE,
        message=f"La herramienta {event.tool_name} falló.",
        technical_detail=event.error,
        retryable=True,
    )


def _validation_event_to_error(event: ToolValidateInputErrorEvent) -> ErrorEntry:
    """CrewAI rejected the tool arguments before calling the tool."""
    return ErrorEntry(
        code=TOOL_FAILURE,
        node="research",
        severity=ErrorSeverity.DEGRADABLE,
        message=(
            f"Los argumentos de la herramienta {event.tool_name} no son válidos. "
            "El agente puede corregirlos en el siguiente intento."
        ),
        technical_detail=str(event.error),
        retryable=True,
    )


def _usage_error_to_error(event: ToolUsageErrorEvent) -> ErrorEntry:
    """A tool raised an exception (not from MCP)."""
    return ErrorEntry(
        code=TOOL_FAILURE,
        node="research",
        severity=ErrorSeverity.DEGRADABLE,
        message=f"La herramienta {event.tool_name} falló.",
        technical_detail=str(event.error),
        retryable=True,
    )


def convert_tool_events(events: list[object]) -> list[ErrorEntry]:
    """Convert a mixed list of captured events to ErrorEntry objects.

    The node collects raw events with ``crewai_event_bus.scoped_handlers()``
    and calls this function once the crew has finished. Events that do not map
    to an error are silently ignored.
    """
    entries: list[ErrorEntry] = []
    for event in events:
        if isinstance(event, MCPToolExecutionFailedEvent):
            entry = _mcp_event_to_error(event)
            if entry is not None:
                entries.append(entry)
        elif isinstance(event, ToolValidateInputErrorEvent):
            entries.append(_validation_event_to_error(event))
        elif isinstance(event, ToolUsageErrorEvent):
            entries.append(_usage_error_to_error(event))
    return entries


# ── Context manager for the crew call (used by the research node in Issue #12) ──


class capture_tool_events:
    """Capture CrewAI tool events while the crew runs, as a context manager.

    Usage in the research node (Issue #12)::

        with capture_tool_events() as captured:
            result = run_step("research", inputs, llm)
        errors = convert_tool_events(captured.events)

    ``captured.events`` is a list of raw CrewAI events, in the order they were
    emitted. ``convert_tool_events()`` turns them into ``ErrorEntry`` objects.
    """

    def __init__(self) -> None:
        self.events: list[object] = []
        self._scope = None

    def __enter__(self) -> "capture_tool_events":
        from crewai.events import crewai_event_bus

        self._scope = crewai_event_bus.scoped_handlers()
        self._scope.__enter__()

        def _remember(source, event):
            self.events.append(event)

        crewai_event_bus.on(MCPToolExecutionFailedEvent)(_remember)
        crewai_event_bus.on(ToolValidateInputErrorEvent)(_remember)
        crewai_event_bus.on(ToolUsageErrorEvent)(_remember)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._scope is not None:
            self._scope.__exit__(exc_type, exc, tb)


class capture_mcp_responses:
    """Capture search_competitors responses from CrewAI MCP events (#12).

    Uso en el nodo research:

        with capture_mcp_responses() as captured:
            result = run_step("research", inputs, llm, tools)
        sources, findings, summary = mcp_response_to_sources_and_findings(
            captured.responses[0], ...  # o bucle si hay varias
        )

    Solo captura el tool "search_competitors". Ignora el resto
    (search_audience_indicators, fetch) y los results que no son dict.
    Usa ``scoped_handlers`` de CrewAI, anidable sin conflicto con
    otros listeners (Majo ya usa uno en main.py).
    """

    def __init__(self) -> None:
        self.responses: list[dict] = []
        self._scope = None

    def __enter__(self) -> "capture_mcp_responses":
        from crewai.events import crewai_event_bus
        from crewai.events.types.mcp_events import MCPToolExecutionCompletedEvent

        self._scope = crewai_event_bus.scoped_handlers()
        self._scope.__enter__()
        crewai_event_bus.on(MCPToolExecutionCompletedEvent)(self._on_event)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._scope is not None:
            self._scope.__exit__(exc_type, exc, tb)

    def _on_event(self, source, event) -> None:
        """Adaptador para el bus de CrewAI (source, event)."""
        self._handle_event(event)

    def _handle_event(self, event) -> None:
        """Filtra y guarda el result si es una respuesta útil."""
        if getattr(event, "tool_name", None) != "search_competitors":
            return
        result = getattr(event, "result", None)
        if isinstance(result, str):
            import json as _json

            try:
                result = _json.loads(result)
            except (ValueError, TypeError):
                return
        if isinstance(result, dict):
            self.responses.append(result)
