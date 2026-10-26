"""MCP client: how TertulIA connects its agents to MCP servers.

This is the only place that says which MCP servers exist, how to start them
and which of their tools each agent may use. The crew gives the tools to an
agent with ``Agent(..., tools=researcher_tools())``.

Under the hood CrewAI does the MCP work: it starts each server, asks for its
tool list (tools/list) and, when the model picks a tool, calls it (tools/call).
"""

import sys
from collections.abc import Callable
from pathlib import Path

from crewai.mcp import MCPClient, MCPServerStdio, MCPToolResolver, create_static_tool_filter
from crewai.mcp.transports.stdio import StdioTransport
from crewai.tools import BaseTool
from crewai.tools.mcp_native_tool import MCPNativeTool
from crewai.utilities.logger import Logger

# client.py lives in <repo>/src/tertulia/mcp/. Paths are absolute, built from
# here, so the servers start the same way whatever folder TertulIA runs from.
SRC_DIR = Path(__file__).resolve().parents[2]
SERVERS_DIR = Path(__file__).resolve().parent / "servers"

# By default CrewAI waits 30 s for a tool and repeats the call up to 3 times.
# A live OpenStreetMap search takes 1-2 minutes (Overpass needs ~35 s per
# query) and our server already retries and falls back to saved data, so:
# one single call, with enough time for all of that to happen.
TOOL_TIMEOUT_S = 150
TOOL_MAX_ATTEMPTS = 1


def neighbourhood_data_server() -> MCPServerStdio:
    """Our own read-only server with Madrid neighbourhood data (OpenStreetMap)."""
    return MCPServerStdio(
        # The same Python that runs TertulIA, so the server uses the project's
        # virtual environment and its installed packages.
        command=sys.executable,
        args=[str(SERVERS_DIR / "neighbourhood_data" / "server.py")],
        # Only what the server needs: finding the tertulia package. Our API keys
        # are not passed on; the server reads its own settings from .env.
        env={"PYTHONPATH": str(SRC_DIR)},
        # Allow list: a tool added to the server later reaches no agent until
        # someone adds it here on purpose (least privilege).
        tool_filter=create_static_tool_filter(allowed_tool_names=["search_competitors"]),
    )


def _patient_client(server: MCPServerStdio) -> Callable[[], MCPClient]:
    """Return a function that opens a new connection to the server when called.

    CrewAI calls it every time the tool is used (one connection per call).
    """

    def new_client() -> MCPClient:
        transport = StdioTransport(command=server.command, args=server.args, env=server.env)
        return MCPClient(
            transport=transport,
            execution_timeout=TOOL_TIMEOUT_S,
            max_retries=TOOL_MAX_ATTEMPTS,
        )

    return new_client


def _tools_from(server: MCPServerStdio) -> list[BaseTool]:
    """Connect once to the server, read its tool list and return CrewAI tools."""
    resolver = MCPToolResolver(agent=None, logger=Logger(verbose=False))
    discovered = resolver.resolve([server])
    # The connection used to read the tool list is no longer needed.
    resolver.cleanup()
    tools: list[BaseTool] = []
    for found in discovered:
        tool = MCPNativeTool(
            client_factory=_patient_client(server),
            tool_name=found.original_tool_name,
            tool_schema={"description": found.description, "args_schema": found.args_schema},
            server_name=found.server_name,
            original_tool_name=found.original_tool_name,
        )
        # CrewAI names MCP tools "<server>_<tool>": with our full paths it is
        # cut to 64 characters and the model would never see
        # "search_competitors". Calls use original_tool_name, so renaming is safe.
        tool.name = found.original_tool_name
        tools.append(tool)
    return tools


def researcher_tools() -> list[BaseTool]:
    """MCP tools for the Researcher agent."""
    return _tools_from(neighbourhood_data_server())