"""Saves REAL API responses for the offline Atocha demo (issue #26).

Usage (from the repo root, with the keys in .env):
    python data/demo_atocha/capture_demo.py --source foursquare
    python data/demo_atocha/capture_demo.py --source google
    python data/demo_atocha/capture_demo.py --source all

Standard library only. Every capture is logged in data/demo_atocha/manifest.json with
its capture date and expiry date. These match the schema fields: ``captured_at`` is
what the graph must use as ``Source.retrieved_at`` and anything read from these files
must be flagged ``Source.from_cache = True``.

READ BEFORE RUNNING (and write it down in docs/fuentes-de-datos.md):
  * Google Places: as far as I could check, the terms only allow storing the place_id
    (no limit) and the coordinates (max. 30 days). This script therefore saves ONLY
    id + location from Google and sets the expiry 30 days ahead; name, rating, etc.
    must be queried live. Confirm the current version of the terms.
  * Foursquare: check their Developer Terms of Service (storage/caching limits) before
    pushing these files to a public repo. Not verified here.
  * If the repo is public, consider adding data/demo_atocha/*.json to .gitignore and
    sharing the captures outside the repo.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

FOLDER = Path(__file__).parent
ATOCHA = (40.4065, -3.6892)  # approx., Atocha station; adjust if needed
FSQ_URL = "https://places-api.foursquare.com/places/search"
FSQ_VERSION = "2025-06-17"
GOOGLE_URL = "https://places.googleapis.com/v1/places:searchText"
QUERIES = {"cafes": "café", "coworking": "coworking"}
GOOGLE_EXPIRY_DAYS = 30


def load_env(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


def _key(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"Falta {name} en .env")
    return value


def _request(req: urllib.request.Request) -> dict:
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        return json.load(resp)


def capture_foursquare(lat: float, lng: float, radius: int) -> dict[str, dict]:
    key = _key("FOURSQUARE_API_KEY")
    out = {}
    for name, query in QUERIES.items():
        params = urllib.parse.urlencode(
            {"query": query, "ll": f"{lat},{lng}", "radius": radius, "limit": 50}
        )
        req = urllib.request.Request(
            f"{FSQ_URL}?{params}",
            headers={
                "Authorization": f"Bearer {key}",
                "X-Places-Api-Version": FSQ_VERSION,
                "Accept": "application/json",
            },
        )
        out[name] = _request(req)
    return out


def capture_google(lat: float, lng: float, radius: int) -> dict[str, dict]:
    key = _key("GOOGLE_PLACES_API_KEY")
    out = {}
    for name, query in QUERIES.items():
        body = {
            "textQuery": query,
            "maxResultCount": 20,
            "locationBias": {
                "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": float(radius)}
            },
        }
        req = urllib.request.Request(
            GOOGLE_URL,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": key,
                # Only id + location: the only fields the terms allow storing.
                "X-Goog-FieldMask": "places.id,places.location",
            },
        )
        out[name] = _request(req)
    return out


def update_manifest(source: str, files: list[str], expires_at: str | None) -> None:
    path = FOLDER / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    manifest[source] = {
        "captured_at": date.today().isoformat(),
        "expires_at": expires_at,  # None = no known expiry (check the terms)
        "files": files,
        "reference_point": {"lat": ATOCHA[0], "lng": ATOCHA[1]},
    }
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def save(source: str, data: dict[str, dict], expires_at: str | None) -> None:
    files = []
    for name, content in data.items():
        filename = f"{source}_{name}.json"
        (FOLDER / filename).write_text(
            json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        files.append(filename)
    update_manifest(source, files, expires_at)
    print(f"[{source}] guardado: {', '.join(files)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--source", choices=["foursquare", "google", "all"], default="all")
    parser.add_argument("--radius", type=int, default=800, help="metres around Atocha")
    args = parser.parse_args()
    load_env()
    lat, lng = ATOCHA

    if args.source in ("foursquare", "all"):
        save("foursquare", capture_foursquare(lat, lng, args.radius), expires_at=None)
    if args.source in ("google", "all"):
        expires = (date.today() + timedelta(days=GOOGLE_EXPIRY_DAYS)).isoformat()
        save("google", capture_google(lat, lng, args.radius), expires_at=expires)


if __name__ == "__main__":
    main()
