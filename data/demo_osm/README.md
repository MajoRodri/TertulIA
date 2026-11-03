# data/demo_osm/ — saved OpenStreetMap data for the demo

Owner: Helen · Issue #30

Saved answers from OpenStreetMap, used by the `neighbourhood_data` MCP server:

- **Demo mode** (`DEMO_MODE=true` in `.env`): the server always answers from these files, instantly and without the internet.
- **Fallback**: if Overpass fails even after the retry, the server answers from these files instead of returning an error.

In both cases every answer says `from_cache: true` and gives the capture date as `retrieved_at`.

## Files

| File | Content |
| --- | --- |
| `atocha.json` | Cafés and coworkings within 2,000 m of the centre of the Atocha barrio |
| `delicias.json` | Cafés and coworkings within 2,000 m of the centre of the Delicias barrio |

They are captured with the **maximum radius (2,000 m)**: the server filters them by distance (haversine), so they work for any radius from 100 to 2,000 m.

## How to update them

From the repo root, with internet (about 6 queries to Overpass, 4–5 minutes):

```bash
python scripts/capture_osm_demo.py
```

`captured_at` in each file (same field name as in `data/demo_atocha/manifest.json`) becomes `Source.retrieved_at`.

## Licence

Data © OpenStreetMap contributors, available under the [Open Database Licence (ODbL)](https://opendatacommons.org/licenses/odbl/). It can be stored and shared as long as the source is credited: every answer of the server includes the attribution.

## Tests

The tests do **not** use these files (they can change when captured again): they use synthetic data in a temporary folder (`tests/test_neighbourhood_data.py`).