import pytest

from tertulia.crew.sector import load_sector
from tertulia.schemas import FindingStatus, compute_confidence
from tertulia.tools.adapters import (
    _fmt,
    artifact_finding,
    break_even_input_from_profile,
    break_even_to_findings,
    mcp_response_to_sources_and_findings,
    trace_from_break_even,
    trace_from_execution,
)
from tertulia.tools.code_exec import GeneratedFile, run_code
from tertulia.tools.punto_equilibrio import compute_break_even


@pytest.fixture
def profile():
    return load_sector("cafe_cowork")


def _all_costs(profile, amount=1000):
    return {item.key: amount for item in profile.fixed_cost_items}


def _findings(profile, **kwargs):
    data = break_even_input_from_profile(profile, **kwargs)
    result = compute_break_even(data)
    labels = {i.key: i.label for i in profile.fixed_cost_items}
    return result, break_even_to_findings(
        result, trace_id="trc-001", unit_label=profile.unit_label, cost_labels=labels
    )


def test_input_takes_unit_and_items_from_the_profile(profile):
    data = break_even_input_from_profile(profile)
    assert data.business_type == "cafe_cowork"
    assert data.unit == profile.unit
    assert [c.item for c in data.fixed_costs] == [i.key for i in profile.fixed_cost_items]
    assert all(c.monthly_amount is None for c in data.fixed_costs)  # nothing invented


def test_unknown_cost_key_is_rejected(profile):
    with pytest.raises(ValueError, match="not in the 'cafe_cowork' profile"):
        break_even_input_from_profile(profile, fixed_costs={"renta": 1000})


def test_known_rent_fills_rent_only_if_no_amount_given(profile):
    data = break_even_input_from_profile(profile, known_rent_eur=2500)
    rent = next(c for c in data.fixed_costs if c.item == "rent")
    assert rent.monthly_amount == 2500 and rent.source == "user_input"
    data = break_even_input_from_profile(
        profile, known_rent_eur=2500, fixed_costs={"rent": 1800}
    )
    assert next(c for c in data.fixed_costs if c.item == "rent").monthly_amount == 1800


def test_nothing_known_gives_only_missing_findings(profile):
    result, findings = _findings(profile)
    assert result.status == "missing"
    assert findings and all(f.status == FindingStatus.MISSING for f in findings)
    assert all(f.value is None for f in findings)
    claims = [f.claim for f in findings]
    assert "Sin dato: Alquiler del local" in claims
    assert "Sin dato: Precio por miembro del cowork" in claims


def test_complete_input_gives_one_finding_per_figure(profile):
    result, findings = _findings(
        profile,
        unit_price=40,
        unit_variable_cost=10,
        fixed_costs=_all_costs(profile, 1000),
        expected_monthly_units=300,
        initial_investment=20000,
    )
    assert result.status == "ok"
    assert [f.id for f in findings] == [f"fnd-{i:03d}" for i in range(1, 8)]
    assert all(f.code_ref == "trc-001" and f.agent == "analyst" for f in findings)
    assert {f.unit for f in findings} == {
        "EUR/month", f"EUR/{profile.unit}", f"{profile.unit}/month",
        f"{profile.unit}/day", "%", "months",
    }  # fmt: skip
    units = next(f for f in findings if f.unit == f"{profile.unit}/month")
    assert units.value == 167 and "167 miembro del cowork al mes" in units.claim


def test_partial_result_adds_note_and_a_missing_finding_per_datum(profile):
    costs = _all_costs(profile, 1000)
    costs["utilities"] = None
    _, findings = _findings(profile, unit_price=40, unit_variable_cost=10, fixed_costs=costs)
    missing = [f for f in findings if f.status == FindingStatus.MISSING]
    assert [f.claim for f in missing] == ["Sin dato: Suministros (luz, agua, internet)"]
    ok = [f for f in findings if f.status == FindingStatus.OK]
    dependent = [f for f in ok if "Margen de contribución" not in f.claim]
    assert dependent and all("resultado parcial" in f.claim for f in dependent)


def test_start_index_continues_the_graph_counter(profile):
    data = break_even_input_from_profile(profile)
    findings = break_even_to_findings(compute_break_even(data), trace_id="trc-004", start_index=12)
    assert findings[0].id == "fnd-012"


def test_unviable_price_is_flagged_in_the_margin_claim(profile):
    _, findings = _findings(
        profile, unit_price=5, unit_variable_cost=10, fixed_costs=_all_costs(profile)
    )
    margin = next(f for f in findings if f.unit == f"EUR/{profile.unit}")
    assert margin.value < 0 and "no cubre el coste variable" in margin.claim


def test_graph_confidence_counts_the_missing_findings(profile):
    _, findings = _findings(profile)
    n_missing = len(findings)
    expected = max(0.0, 1 - 0.1 * n_missing)
    assert compute_confidence(findings, []) == pytest.approx(expected, abs=0.01)


def test_accepts_the_dict_returned_by_the_tool(profile):
    from tertulia.tools.punto_equilibrio import break_even_tool

    out = break_even_tool(
        business_type="cafe_cowork", unit="member", unit_price=40, unit_variable_cost=10,
        fixed_costs=[{"item": "rent", "monthly_amount": 1500}],
    )  # fmt: skip
    findings = break_even_to_findings(out, trace_id="trc-002")
    assert findings and findings[0].id == "fnd-001"


def test_number_format_is_spanish():
    assert _fmt(1234.5) == "1.234,5"
    assert _fmt(500) == "500"
    assert _fmt(16.67) == "16,67"


def test_trace_from_execution_keeps_the_full_script(tmp_path):
    code = "print(21 * 2)"
    result = run_code(code, outputs_root=tmp_path)
    trace = trace_from_execution(result, trace_id="trc-003", finding_ids=["fnd-001"])
    assert trace.code == code and trace.error is None
    assert trace.output["stdout"].strip() == "42"
    assert trace.tool == "code_exec" and trace.finding_ids == ["fnd-001"]


def test_trace_from_failed_execution_records_the_error(tmp_path):
    trace = trace_from_execution(run_code("1 / 0", outputs_root=tmp_path), trace_id="trc-004")
    assert trace.error and trace.error.startswith("exception:")


def test_trace_from_break_even_stores_inputs_and_output(profile):
    data = break_even_input_from_profile(profile, unit_price=40, unit_variable_cost=10)
    trace = trace_from_break_even(data, compute_break_even(data), trace_id="trc-005")
    assert trace.inputs["business_type"] == "cafe_cowork"
    assert trace.output["status"] == "missing" and "fixed_costs" in trace.code


def test_artifact_finding_points_to_the_chart():
    chart = GeneratedFile(
        name="b.png", path="outputs/run-001/ab_b.png",
        relative_path="run-001/ab_b.png", size_bytes=10,
    )  # fmt: skip
    finding = artifact_finding(
        chart, "Gráfico del punto de equilibrio", finding_id="fnd-009", trace_id="trc-003"
    )
    assert finding.artifact_paths == ["run-001/ab_b.png"] and finding.value is None

def test_build_cost_labels_from_profile():
    from tertulia.crew.sector import load_sector
    from tertulia.tools.adapters import build_cost_labels

    profile = load_sector("cafe_cowork")
    labels = build_cost_labels(profile)
    assert labels["rent"] == "Alquiler del local"
    assert "staff" in labels
    assert len(labels) == len(profile.fixed_cost_items)


def test_mcp_response_basic():
    response = {
        "category": "cafe",  # raw value from the MCP server
        "total": 12,
        "confirmed_count": 8,
        "needs_review_count": 2,
        "foursquare_status": "not_used",
    }
    sources, findings, summary = mcp_response_to_sources_and_findings(response)
    assert len(sources) == 1  # OSM only
    assert sources[0].id == "src-001"
    assert any(f.value == 8 for f in findings)
    assert any(f.value == 2 for f in findings)
    confirmed_finding = next(f for f in findings if f.value == 8)
    assert "cafeterías confirmadas" in confirmed_finding.claim  # feminine agreement
    assert "cafeterías" in summary


def test_mcp_response_with_foursquare_adds_second_source():
    response = {
        "category": "bares",
        "total": 5,
        "confirmed_count": 3,
        "foursquare_status": "used",
    }
    sources, findings, _ = mcp_response_to_sources_and_findings(response)
    assert len(sources) == 2
    titles = {s.title for s in sources}
    assert "Foursquare Places API" in titles


def test_mcp_response_start_index_is_respected():
    response = {"category": "coworking", "total": 4, "confirmed_count": 4}
    sources, findings, _ = mcp_response_to_sources_and_findings(
        response, start_source_index=3, start_finding_index=7
    )
    assert sources[0].id == "src-003"
    assert findings[0].id == "fnd-007"
