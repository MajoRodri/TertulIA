"""Tests del adapter MCP y del context manager capture_mcp_responses (Issue #12).

Fakean los eventos del bus de CrewAI para no llamar a servidores reales.
"""

from tertulia.graph.tool_events import capture_mcp_responses
from tertulia.schemas import FindingStatus, SourceType
from tertulia.tools.adapters import (
    findings_to_summary,
    mcp_response_to_sources_and_findings,
)

# --- Helpers ---------------------------------------------------------------------


def _venue(name, *, needs_review=False, sources=None, review_reason=None, suspicious=False):
    return {
        "name": name,
        "brand": None,
        "address": None,
        "lat": 40.4,
        "lon": -3.68,
        "opening_hours": None,
        "check_date": None,
        "osm_url": f"https://www.openstreetmap.org/node/{name}",
        "sources": sources or ["osm"],
        "foursquare_id": None,
        "foursquare_url": None,
        "foursquare_categories": [],
        "needs_review": needs_review,
        "review_reason": review_reason,
        "suspicious": suspicious,
        "injection_patterns": [],
    }


def _response(
    *,
    category="coworking",
    total=10,
    confirmed_count=2,
    needs_review_count=8,
    foursquare_status="used",
    coverage_note=None,
    venues=None,
    from_cache=False,
    retrieved_at="2026-10-29T10:00:00+00:00",
    foursquare_limit_reached=False,
):
    if venues is None:
        venues = [
            _venue("Spaces"),
            _venue("Utopicus"),
            _venue(
                "Repsol",
                needs_review=True,
                sources=["foursquare"],
                review_reason="Solo aparece en Foursquare",
            ),
        ]
    return {
        "neighbourhood": "Atocha",
        "category": category,
        "centre": {"lat": 40.4, "lon": -3.68},
        "radius_m": 800,
        "total": total,
        "suspicious_count": 0,
        "needs_review_count": needs_review_count,
        "confirmed_count": confirmed_count,
        "venues": venues,
        "source": "OpenStreetMap, via the Overpass API",
        "attribution": "© OpenStreetMap contributors (ODbL)",
        "foursquare_status": foursquare_status,
        "foursquare_limit_reached": foursquare_limit_reached,
        "coverage_note": coverage_note,
        "retrieved_at": retrieved_at,
        "from_cache": from_cache,
    }


class _FakeEvent:
    """Lo mínimo que lee el handler: tool_name y result."""

    def __init__(self, tool_name, result):
        self.tool_name = tool_name
        self.result = result


# --- capture_mcp_responses -------------------------------------------------------


def test_capture_keeps_search_competitors_responses():
    response = _response()
    with capture_mcp_responses() as captured:
        captured._handle_event(_FakeEvent("search_competitors", response))
    assert captured.responses == [response]


def test_capture_ignores_other_tools():
    with capture_mcp_responses() as captured:
        captured._handle_event(_FakeEvent("search_audience_indicators", {"x": 1}))
        captured._handle_event(_FakeEvent("fetch", "page"))
    assert captured.responses == []


def test_capture_parses_json_string_results():
    import json

    response = _response()
    with capture_mcp_responses() as captured:
        captured._handle_event(_FakeEvent("search_competitors", json.dumps(response)))
    assert captured.responses == [response]


def test_capture_ignores_non_dict_results():
    with capture_mcp_responses() as captured:
        captured._handle_event(_FakeEvent("search_competitors", "not json"))
        captured._handle_event(_FakeEvent("search_competitors", None))
        captured._handle_event(_FakeEvent("search_competitors", [1, 2, 3]))
    assert captured.responses == []


# --- mcp_response_to_sources_and_findings ----------------------------------------


def test_osm_source_is_always_created():
    sources, _findings, _summary = mcp_response_to_sources_and_findings(_response())
    osm = [s for s in sources if s.source_type == SourceType.OPEN_DATA]
    assert len(osm) == 1
    assert osm[0].url == "https://www.openstreetmap.org/"
    assert osm[0].retrieved_by == "mcp.osm_search"


def test_foursquare_source_is_created_when_used():
    sources, _findings, _summary = mcp_response_to_sources_and_findings(
        _response(foursquare_status="used")
    )
    fsq = [s for s in sources if s.source_type == SourceType.API]
    assert len(fsq) == 1
    assert fsq[0].from_cache is False


def test_foursquare_source_is_skipped_when_not_used():
    sources, _findings, _summary = mcp_response_to_sources_and_findings(
        _response(foursquare_status="not_used", needs_review_count=0)
    )
    fsq = [s for s in sources if s.source_type == SourceType.API]
    assert fsq == []


def test_confirmed_finding_has_value_and_unit():
    _sources, findings, _summary = mcp_response_to_sources_and_findings(
        _response(category="coworking", confirmed_count=2, total=10)
    )
    confirmed = [f for f in findings if "confirmad" in f.claim.lower()]
    assert len(confirmed) == 1
    assert confirmed[0].value == 2
    assert confirmed[0].unit == "coworking"
    assert confirmed[0].status == FindingStatus.OK


def test_needs_review_finding_is_created_when_count_positive():
    _sources, findings, _summary = mcp_response_to_sources_and_findings(
        _response(needs_review_count=8)
    )
    pending = [f for f in findings if "revisión" in f.claim.lower() or "revisar" in f.claim.lower()]
    assert len(pending) >= 1
    global_pending = [f for f in pending if f.value == 8]
    assert len(global_pending) == 1


def test_coverage_note_creates_finding_when_present():
    note = "No se consultó Foursquare: puede haber más coworkings de los listados."
    _sources, findings, _summary = mcp_response_to_sources_and_findings(
        _response(foursquare_status="not_used", coverage_note=note)
    )
    coverage = [f for f in findings if f.claim == note]
    assert len(coverage) == 1
    assert coverage[0].value is None


def test_needs_review_venue_creates_one_finding_each():
    venues = [
        _venue("Spaces"),
        _venue("Repsol", needs_review=True, sources=["foursquare"], review_reason="Solo aparece en Foursquare"),
        _venue("IBM Cloud", needs_review=True, sources=["foursquare"], review_reason="Solo aparece en Foursquare"),
    ]
    _sources, findings, _summary = mcp_response_to_sources_and_findings(
        _response(venues=venues, needs_review_count=2)
    )
    venue_findings = [f for f in findings if "Repsol" in f.claim or "IBM Cloud" in f.claim]
    assert len(venue_findings) == 2
    for f in venue_findings:
        assert f.status == FindingStatus.OK
        assert f.value is None


def test_suspicious_venues_do_not_create_findings():
    venues = [
        _venue("Spaces"),
        _venue("Bad Actor", needs_review=True, suspicious=True, review_reason="Flagged"),
    ]
    _sources, findings, _summary = mcp_response_to_sources_and_findings(
        _response(venues=venues, needs_review_count=1)
    )
    assert all("Bad Actor" not in f.claim for f in findings)


def test_from_cache_propagates_to_osm_source():
    sources, _findings, _summary = mcp_response_to_sources_and_findings(
        _response(from_cache=True)
    )
    osm = [s for s in sources if s.source_type == SourceType.OPEN_DATA][0]
    assert osm.from_cache is True


# --- findings_to_summary ---------------------------------------------------------


def test_findings_to_summary_contains_counts_and_coverage():
    _sources, findings, _summary = mcp_response_to_sources_and_findings(
        _response(
            category="coworking",
            confirmed_count=2,
            needs_review_count=8,
            total=10,
            foursquare_status="not_used",
            coverage_note="No se consultó Foursquare.",
        )
    )
    summary = findings_to_summary(findings, category="coworking")
    assert "2" in summary
    assert "8" in summary
    assert "10" in summary
    assert "No se consultó Foursquare" in summary
