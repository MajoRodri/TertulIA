"""One-off test: are there more coworkings in Foursquare than in OpenStreetMap?

Two API calls (800 m and 2,000 m), around the SAME centre our MCP server uses
(the centre of the Atocha barrio, read from data/demo_osm/atocha.json), so the
comparison is fair. Nothing is saved: it only prints. Not part of the project.

Run it from the repo root, with FOURSQUARE_API_KEY in your .env:
    python outputs/pruebas/compare_coworkings.py
"""

import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

FSQ_URL = "https://places-api.foursquare.com/places/search"
FSQ_VERSION = "2025-06-17"  # the same as Yohanna's capture script
RADII_M = (800, 2000)


def read_key() -> str:
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "FOURSQUARE_API_KEY" and value.strip():
            return value.split("#")[0].strip().strip('"')
    raise SystemExit("FOURSQUARE_API_KEY is missing in your .env")


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi, d_lambda = phi2 - phi1, math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def foursquare(lat: float, lon: float, radius: int, key: str) -> list[dict]:
    params = urllib.parse.urlencode(
        {"query": "coworking", "ll": f"{lat},{lon}", "radius": radius, "limit": 50}
    )
    request = urllib.request.Request(
        f"{FSQ_URL}?{params}",
        headers={
            "Authorization": f"Bearer {key}",
            "X-Places-Api-Version": FSQ_VERSION,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response).get("results", [])


def main() -> None:
    osm = json.loads(Path("data/demo_osm/atocha.json").read_text(encoding="utf-8"))
    lat, lon = osm["centre"]["lat"], osm["centre"]["lon"]
    key = read_key()
    for radius in RADII_M:
        in_osm = [
            venue["name"]
            for venue in osm["venues"]["coworking"]
            if distance_m(lat, lon, venue["lat"], venue["lon"]) <= radius
        ]
        in_fsq = foursquare(lat, lon, radius, key)
        print(f"\n===== {radius} m around the centre of Atocha =====")
        print(f"OpenStreetMap: {len(in_osm)} coworkings")
        print(
            f"Foursquare:    {len(in_fsq)} results"
            + (" (limit reached: there may be more)" if len(in_fsq) == 50 else "")
        )
        for place in in_fsq:
            categories = ", ".join(c.get("name", "") for c in place.get("categories", []))
            print(f"  - {place.get('name')} ({place.get('distance', '?')} m) [{categories}]")


if __name__ == "__main__":
    main()