"""Tests for the MCP client (src/tertulia/mcp/client.py).

They never start a server: the part of CrewAI that reads the tool list is
replaced by a fake, so the tests check only our own decisions.
"""

import sys
from types import SimpleNamespace

from pydantic import BaseModel

from tertulia.mcp import client


class _FakeArgs(BaseModel):
    neighbourhood: str


def _fake_discovered_tool():
    """What CrewAI's resolver returns: a long, cut name and the original one."""
    return SimpleNamespace(
        name="usr_bin_python3_very_long_path_server_py_search_compet_1a2b3c4d",
        original_tool_name="search_competitors",
        description="Find competitor venues around a Madrid barrio or district.",
        args_schema=_FakeArgs,
        server_name="python_server.py",
    )


class _FakeResolver:
    """Stands in for MCPToolResolver: no process is started."""

    cleaned_up = False

    def __init__(self, agent, logger):
        pass

    def resolve(self, servers):
        return [_fake_discovered_tool()]

    def cleanup(self):
        _FakeResolver.cleaned_up = True


# --- 1. Where the kitchen is: how the server is started --------------------------


def test_server_runs_with_the_project_python_and_its_own_file():
    config = client.neighbourhood_data_server()
    assert config.command == sys.executable
    server_file = client.SERVERS_DIR / "neighbourhood_data" / "server.py"
    assert config.args == [str(server_file)]
    assert server_file.is_file()


def test_server_gets_only_pythonpath_and_no_api_keys():
    config = client.neighbourhood_data_server()
    # Least privilege: nothing else from our environment (API keys...) is passed.
    assert set(config.env) == {"PYTHONPATH"}
    assert (client.SRC_DIR / "tertulia").is_dir()


def test_only_allowed_tools_reach_the_agents():
    allowed = client.neighbourhood_data_server().tool_filter
    assert allowed({"name": "search_competitors"}) is True
    assert allowed({"name": "delete_everything"}) is False


# --- 2. Copying the menu: tools with their real name ---------------------------


def test_tools_keep_their_original_name(monkeypatch):
    monkeypatch.setattr(client, "MCPToolResolver", _FakeResolver)
    tools = client.researcher_tools()
    assert [tool.name for tool in tools] == ["search_competitors"]
    assert tools[0].description.startswith("Find competitor venues")
    assert _FakeResolver.cleaned_up is True  # the discovery connection is closed


# --- 3. A patient waiter: one long call, no repetitions -------------------------


def test_tool_calls_wait_long_enough_and_are_not_repeated(monkeypatch):
    monkeypatch.setattr(client, "MCPToolResolver", _FakeResolver)
    tool = client.researcher_tools()[0]
    # Creating the client does not start the server: that happens on connect().
    connection = tool._client_factory()
    assert connection.execution_timeout == client.TOOL_TIMEOUT_S == 150
    assert connection.max_retries == client.TOOL_MAX_ATTEMPTS == 1
