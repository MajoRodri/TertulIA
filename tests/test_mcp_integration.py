"""Integration test: the real neighbourhood_data server, through MCP and CrewAI.

The other tests replace parts with fakes. This one starts the real server and
checks the error exactly as the graph will receive it: in CrewAI's
MCPToolExecutionFailedEvent. It needs no internet: an unknown category is
rejected before any search. It takes a few seconds (the server starts).
"""

from crewai.events import crewai_event_bus
from crewai.events.types.mcp_events import MCPToolExecutionFailedEvent

from tertulia.mcp import client


def test_the_graph_receives_our_error_code_in_the_mcp_event():
    failures = []
    # scoped_handlers: our listener only exists inside this block.
    with crewai_event_bus.scoped_handlers():

        @crewai_event_bus.on(MCPToolExecutionFailedEvent)
        def remember(source, event):
            failures.append(event)

        tool = client._tools_from(client.neighbourhood_data_server())[0]
        tool.run(neighbourhood="Atocha", category="bar")

    assert len(failures) == 1
    event = failures[0]
    assert event.tool_name == "search_competitors"
    assert event.error_type == "tool_error"
    assert client.error_code(event.error) == "invalid_input"