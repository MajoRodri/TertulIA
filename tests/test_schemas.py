from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from tertulia.schemas import (
    BusinessBrief,
    Finding,
    FindingStatus,
    Source,
    SourceType,
    TraceEntry,
    TrafficLight,
    Verdict,
    compute_confidence,
)


def test_brief_defaults_to_madrid_and_analyst():
    brief = BusinessBrief(business_type="cafe_cowork", neighbourhood="Atocha")
    assert brief.city == "Madrid"
    assert brief.user_profile == "analyst"


def test_brief_has_no_images_by_default():
    brief = BusinessBrief(business_type="cafe_cowork", neighbourhood="Atocha")
    assert brief.image_paths == []


def test_brief_accepts_uploaded_photos():
    paths = ["run-001/uploads/front.jpg", "run-001/uploads/menu.PNG"]
    brief = BusinessBrief(business_type="cafe_cowork", neighbourhood="Atocha", image_paths=paths)
    assert brief.image_paths == paths

def test_brief_paths_are_relative_to_outputs():
    # Any folder inside outputs/ is valid: "photo.jpg" is outputs/photo.jpg.
    paths = ["photo.jpg", "other_folder/photo.jpeg"]
    brief = BusinessBrief(business_type="cafe_cowork", neighbourhood="Atocha", image_paths=paths)
    assert brief.image_paths == paths

@pytest.mark.parametrize(
    "path",
    [
        "../.env",  # goes up out of outputs/
        "run-001/../../secrets.png",
        "/etc/passwd.png",  # absolute path
        "C:/Users/helen/photo.jpg",  # Windows drive
        "run-001\\..\\..\\photo.jpg",  # Windows separators
        "run-001/uploads/menu.pdf",  # not an image (PDFs: later)
        "run-001/uploads/photo",  # no extension
    ],
)
def test_brief_rejects_unsafe_or_non_image_paths(path):
    with pytest.raises(ValidationError):
        BusinessBrief(business_type="cafe_cowork", neighbourhood="Atocha", image_paths=[path])


def test_brief_accepts_at_most_ten_photos():
    paths = [f"run-001/uploads/photo_{n}.jpg" for n in range(11)]
    with pytest.raises(ValidationError):
        BusinessBrief(business_type="cafe_cowork", neighbourhood="Atocha", image_paths=paths)


def test_external_source_needs_url():
    with pytest.raises(ValidationError):
        Source(
            id="src-001",
            source_type=SourceType.WEB,
            title="Competitor site",
            retrieved_at=datetime(2026, 10, 21, tzinfo=UTC),
            retrieved_by="mcp.fetch",
        )


def test_user_input_source_without_url_is_valid():
    source = Source(
        id="src-002",
        source_type=SourceType.USER_INPUT,
        title="Rent given by the client",
        retrieved_at=datetime(2026, 10, 21, tzinfo=UTC),
        retrieved_by="ui",
    )
    assert source.url is None


def test_finding_without_source_or_code_is_rejected():
    with pytest.raises(ValidationError):
        Finding(id="fnd-001", claim="Average coffee price", value=2.1, agent="analyst")


def test_finding_with_code_ref_is_valid():
    finding = Finding(
        id="fnd-002",
        claim="Average coffee price",
        value=2.1,
        unit="EUR",
        code_ref="code_exec#3",
        agent="analyst",
    )
    assert finding.status == FindingStatus.OK


def test_missing_finding_cannot_have_value():
    with pytest.raises(ValidationError):
        Finding(
            id="fnd-003",
            claim="Rent per m2",
            value=25,
            status=FindingStatus.MISSING,
            agent="researcher",
        )


def test_verdict_needs_a_reason_and_starts_unapproved():
    with pytest.raises(ValidationError):
        Verdict(light=TrafficLight.GREEN, confidence=0.8, summary="Go", reasons=[])
    verdict = Verdict(
        light=TrafficLight.AMBER, confidence=0.6, summary="Maybe", reasons=["High rent"]
    )
    assert verdict.approved_by_human is False


def _source(n, suspicious=False):
    return Source(
        id=f"src-00{n}",
        source_type=SourceType.OPEN_DATA,
        title="Census",
        url="https://datos.madrid.es",
        retrieved_at=datetime(2026, 10, 21, tzinfo=UTC),
        retrieved_by="mcp.open_data",
        suspicious=suspicious,
    )


def test_cached_source_keeps_capture_date():
    source = _source(1).model_copy(update={"from_cache": True})
    assert source.from_cache is True
    assert source.retrieved_at.day == 21


def test_finding_can_carry_chart_paths():
    finding = Finding(
        id="fnd-004",
        claim="Hacen falta 38 miembros al mes",
        value=38,
        unit="members/month",
        code_ref="trc-003",
        artifact_paths=["run-001/charts/break_even.png"],
        agent="analyst",
    )
    assert finding.artifact_paths == ["run-001/charts/break_even.png"]


def test_override_needs_a_reason():
    with pytest.raises(ValidationError):
        Verdict(
            light=TrafficLight.AMBER,
            confidence=0.6,
            summary="Maybe",
            reasons=["High rent"],
            light_override=TrafficLight.GREEN,
        )


def test_override_keeps_both_values():
    verdict = Verdict(
        light=TrafficLight.AMBER,
        confidence=0.62,
        summary="Maybe",
        reasons=["High rent"],
        light_override=TrafficLight.GREEN,
        confidence_override=0.75,
        override_reason="Conozco el local y el alquiler real es más bajo",
    )
    assert verdict.light == "amber" and verdict.final_light == "green"
    assert verdict.confidence == 0.62 and verdict.final_confidence == 0.75
    assert verdict.model_dump()["final_light"] == "green"


def test_without_override_final_values_are_the_system_ones():
    verdict = Verdict(light=TrafficLight.RED, confidence=0.4, summary="No", reasons=["x"])
    assert verdict.final_light == "red" and verdict.final_confidence == 0.4


def test_compute_confidence_penalises_missing_and_suspicious():
    findings = [
        Finding(id="fnd-001", claim="a", value=1, code_ref="trc-001", agent="analyst"),
        Finding(id="fnd-002", claim="b", status=FindingStatus.MISSING, agent="researcher"),
    ]
    sources = [_source(1), _source(2, suspicious=True)]
    assert compute_confidence(findings, sources) == 0.85
    assert compute_confidence([], []) == 1.0


def test_trace_entry_stores_the_code():
    entry = TraceEntry(
        id="trc-003",
        timestamp=datetime(2026, 10, 21, tzinfo=UTC),
        actor="analyst",
        tool="code_exec",
        code="print(1 + 1)",
        output="2",
        finding_ids=["fnd-004"],
    )
    assert entry.code == "print(1 + 1)"