"""Capture OpenStreetMap audience places for the offline demo.

Run it once, with internet, from the repo root:
    python scripts/capture_audience_demo.py

It saves data/demo_osm/audience/<neighbourhood>.json with every place within the
maximum radius, so the server can later serve any smaller radius offline by
filtering by distance. Only the tags the tool uses are kept. Data ©
OpenStreetMap contributors, ODbL licence: it can be stored as long as the
source is credited.
"""

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# The server is run as a script, not installed as a package: make it importable.
sys.path[:0] = ["src", "src/tertulia/mcp/servers/neighbourhood_data"]

import server  # noqa: E402
from server import (  # noqa: E402
    ATTRIBUTION,
    AUDIENCE_RULES,
    MAX_RADIUS_M,
    _audience_query,
    _find_centre,
    _run_query,
    _to_place,
)

NEIGHBOURHOODS = ("Atocha", "Delicias")
OUTPUT_DIR = Path("data/demo_osm/audience")
# The tags the tool reads: the rule keys, the name and the website.
KEPT_TAGS = {key for _, key, _ in AUDIENCE_RULES} | {"name", "website", "contact:website"}
# 2000 m of restaurants, offices... is a heavy query (on 28 Oct it timed out at
# 60 s). A one-off capture can wait longer than a live tool call.
CAPTURE_TIMEOUT_S = 180


def capture(neighbourhood: str) -> dict:
    """Ask Overpass for every audience place around one neighbourhood."""
    lat, lon = _find_centre(neighbourhood)
    server.TIMEOUT_S = CAPTURE_TIMEOUT_S  # only for this script, not for the tool
    query = _audience_query(lat, lon, MAX_RADIUS_M).replace(
        "[timeout:50]", f"[timeout:{CAPTURE_TIMEOUT_S - 10}]"
    )
    elements = _run_query(query, time.monotonic() + 2 * CAPTURE_TIMEOUT_S + 30)
    places = []
    for element in elements:
        place = _to_place(element)
        if place:
            place["tags"] = {k: v for k, v in place["tags"].items() if k in KEPT_TAGS}
            places.append(place)
    return {
        "neighbourhood": neighbourhood,
        "centre": {"lat": lat, "lon": lon},
        "radius_m": MAX_RADIUS_M,
        "places": places,
        "captured_at": datetime.now(UTC).isoformat(),
        "attribution": ATTRIBUTION,
    }


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in NEIGHBOURHOODS:
        data = capture(name)
        path = OUTPUT_DIR / f"{name.lower()}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{name}: {len(data['places'])} places saved in {path}")