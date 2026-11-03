"""Tests for the CrewAI tool events to ErrorEntry mapping (Issue #14)."""

from crewai.events.types.mcp_events import MCPToolExecutionFailedEvent
from crewai.events.types.tool_usage_events import (
    ToolUsageErrorEvent,
    ToolValidateInputErrorEvent,
)

from tertulia.graph.errors import (
    MISSING_DATA,
    TOOL_FAILURE,
    TOOL_TIMEOUT,
    ErrorSeverity,
)
from tertulia.graph.tool_events import convert_tool_events


def _mcp_failed(error: str, error_type: str = "tool_error", tool: str = "search_competitors"):
    return MCPToolExecutionFailedEvent(
        server_name="neighbourhood_data",
        server_url="stdio://neighbourhood_data",
        transport_type="stdio",
        tool_name=tool,
        tool_args={"neighbourhood": "Atocha", "category": "bar"},
        error=error,
        error_type=error_type,
    )


def test_invalid_input_maps_to_tool_failure():
    event = _mcp_failed(
        "Error executing tool search_competitors: [invalid_input] Unknown category: 'bar'"
    )
    entries = convert_tool_events([event])
    assert len(entries) == 1
    assert entries[0].code == TOOL_FAILURE
    assert entries[0].node == "research"
    assert entries[0].severity == ErrorSeverity.DEGRADABLE
    assert entries[0].retryable is False


def test_not_found_maps_to_missing_data():
    event = _mcp_failed("Error executing tool search_competitors: [not_found] Narnia")
    entries = convert_tool_events([event])
    assert len(entries) == 1
    assert entries[0].code == MISSING_DATA
    assert entries[0].retryable is False


def test_source_unavailable_maps_to_tool_timeout():
    event = _mcp_failed(
        "Error executing tool search_competitors: [source_unavailable] no saved data"
    )
    entries = convert_tool_events([event])
    assert len(entries) == 1
    assert entries[0].code == TOOL_TIMEOUT
    assert entries[0].retryable is True


def test_timeout_error_type_maps_to_tool_timeout():
    event = _mcp_failed("Tool execution timed out", error_type="timeout")
    entries = convert_tool_events([event])
    assert len(entries) == 1
    assert entries[0].code == TOOL_TIMEOUT


def test_unknown_mcp_error_falls_back_to_tool_failure():
    event = _mcp_failed("Error executing tool x: something odd", error_type="server_error")
    entries = convert_tool_events([event])
    assert len(entries) == 1
    assert entries[0].code == TOOL_FAILURE


def test_validation_error_maps_to_tool_failure():
    event = ToolValidateInputErrorEvent(
        tool_name="search_competitors",
        tool_args={"radius_m": "lejos"},
        tool_class="MCPNativeTool",
        error="arguments validation failed",
    )
    entries = convert_tool_events([event])
    assert len(entries) == 1
    assert entries[0].code == TOOL_FAILURE
    assert "search_competitors" in entries[0].message
    assert entries[0].retryable is True


def test_usage_error_maps_to_tool_failure():
    event = ToolUsageErrorEvent(
        tool_name="fetch",
        tool_args={"url": "https://example.com"},
        error="connection refused",
    )
    entries = convert_tool_events([event])
    assert len(entries) == 1
    assert entries[0].code == TOOL_FAILURE
    assert "fetch" in entries[0].message


def test_mixed_events_are_all_converted():
    events = [
        _mcp_failed("Error executing tool x: [not_found] nope"),
        ToolValidateInputErrorEvent(
            tool_name="search_competitors",
            tool_args={},
            tool_class="MCPNativeTool",
            error="arguments validation failed",
        ),
    ]
    entries = convert_tool_events(events)
    assert len(entries) == 2
    assert {e.code for e in entries} == {MISSING_DATA, TOOL_FAILURE}


def test_empty_list_returns_empty_list():
    assert convert_tool_events([]) == []


def test_messages_are_in_spanish():
    event = _mcp_failed("Error executing tool x: [not_found] nope")
    entries = convert_tool_events([event])
    assert "No se encontraron datos" in entries[0].message
