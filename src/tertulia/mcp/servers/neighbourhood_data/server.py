"""datos_local: our MCP server with read-only tools about Madrid neighbourhoods.

Step 3a: a minimal version with FAKE data, only to see MCP working.
Step 3b will replace the fake data with real OpenStreetMap data.
Written for the MCP Python SDK 1.x (the version CrewAI uses).
"""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

server = FastMCP(name="neighbourhood_data")

FAKE_VENUES = {
    "atocha": [
        {"name": "Café de Prueba", "category": "cafe"},
        {"name": "Cowork de Prueba", "category": "coworking"},
    ],
}


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def search_competitors(neighbourhood: str, category: str = "cafe") -> list[dict]:
    """Find venues of a category in a Madrid neighbourhood (fake data for now)."""
    venues = FAKE_VENUES.get(neighbourhood.lower(), [])
    return [v for v in venues if v["category"] == category]


if __name__ == "__main__":
    server.run()  # stdio by default