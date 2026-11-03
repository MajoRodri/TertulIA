"""Capture OpenStreetMap venues for the offline demo (step 3b-3).

Run it once, with internet, from the repo root:
    python scripts/capture_osm_demo.py

It saves data/demo_osm/<neighbourhood>.json with every category within the
maximum radius, so the server can later serve any smaller radius offline by
filtering by distance. Data © OpenStreetMap contributors, ODbL licence: it can
be stored as long as the source is credited.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# The server is run as a script, not installed as a package: make it importable.
sys.path[:0] = ["src", "src/tertulia/mcp/servers/neighbourhood_data"]

from server import (  # noqa: E402
    ATTRIBUTION,
    CATEGORY_TAGS,
    MAX_RADIUS_M,
    _find_centre,
    _search_venues,
)

NEIGHBOURHOODS = ("Atocha", "Delicias")
OUTPUT_DIR = Path("data/demo_osm")


def capture(neighbourhood: str) -> dict:
    """Ask Overpass for every category around one neighbourhood."""
    lat, lon = _find_centre(neighbourhood)
    venues = {
        category: _search_venues(lat, lon, category, MAX_RADIUS_M)
        for category in CATEGORY_TAGS
    }
    return {
        "neighbourhood": neighbourhood,
        "centre": {"lat": lat, "lon": lon},
        "radius_m": MAX_RADIUS_M,
        "venues": venues,
        "source": "OpenStreetMap, via the Overpass API",
        "attribution": ATTRIBUTION,
        # Same field name as Yohanna's manifest: it becomes Source.retrieved_at.
        "captured_at": datetime.now(UTC).isoformat(),
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in NEIGHBOURHOODS:
        data = capture(name)
        path = OUTPUT_DIR / f"{name.lower()}.json"
        # ensure_ascii=False keeps accents readable instead of turning them into
        # escape codes, so the file can be checked by eye.
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        counts = ", ".join(f"{len(found)} {category}" for category, found in data["venues"].items())
        print(f"{name}: {counts} -> {path}")


if __name__ == "__main__":
    main()