"""Small client to try the datos_local MCP server from the terminal.

Run from the repo root:  python scripts/try_mcp_server.py
"""

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = StdioServerParameters(
    command=sys.executable,
    args=["src/tertulia/mcp/servers/neighbourhood_data/server.py"],
    env={**os.environ, "PYTHONPATH": "src"},
)


async def main() -> None:
    # Start the server as a subprocess and talk to it through stdin/stdout
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()  # the initial "handshake"

            # 1. tools/list: ask the server for its "menu"
            tools = await session.list_tools()
            for tool in tools.tools:
                print("TOOL:", tool.name, "-", tool.description)
                print("INPUT SCHEMA:", json.dumps(tool.inputSchema, indent=2))

            # 2. tools/call: order a "dish"
            result = await session.call_tool(
                "search_competitors", {"neighbourhood": "Atocha", "category": "cafe"}
            )
            for item in result.content:
                print("RESULT:", item.text)

            # 3. tools/call with a missing argument: the input schema rejects it
            wrong = await session.call_tool("search_competitors", {"category": "cafe"})
            print("ERROR?", wrong.isError, "-", wrong.content[0].text[:120])


asyncio.run(main())
