"""Tests del nodo vision_charts (Issue #12).

Mockean analyse_image y llm_from_settings para no llamar al modelo real.
"""

import pytest

from tertulia.graph.errors import TOOL_FAILURE, ErrorSeverity
from tertulia.graph.nodes import vision_charts_node
from tertulia.graph.state import AgentState
from tertulia.schemas import Finding
from tertulia.vision.loader import ImageRejected
from tertulia.vision.tool import AnalysisFailed
from tertulia.vision.vision_schemas import (
    Category,
    Confidence,
    ImageAnalysis,
    ImageKind,
)


def _analysis(path: str, kind: ImageKind = ImageKind.CHART, observations=None, **overrides) -> ImageAnalysis:
    if observations is None:
        observations = [
            {
                "category": Category.CAPACITY,
                "observation": "El gráfico muestra un punto de equilibrio de 68 clientes al día",
                "confidence": Confidence.HIGH,
            }
        ]
    data = {
        "kind": kind,
        "observations": observations,
        "visible_text": [],
        "people_visible": False,
        "unclear": None,
        "image_path": path,
    }
    return ImageAnalysis(**{**data, **overrides})


def _state_with_chart(path: str = "run-1/charts/break_even.png") -> AgentState:
    return {
        "request": None,  # type: ignore[typeddict-item]
        "sources": [],
        "findings": [
            Finding(
                id="fnd-001",
                claim="Punto de equilibrio calculado",
                agent="analyst",
                code_ref="trc-001",
                artifact_paths=[path],
            )
        ],
        "draft_report": "",
        "review_round": 0,
        "reviewer_comments": [],
        "verdict": None,
        "traces": [],
        "tokens_used": 0,
        "human_approved": False,
        "expired": False,
        "errors": [],
        "research_result": "",
        "vision_result": "",
        "analysis_result": "",
    }


def _state_without_charts() -> AgentState:
    state = _state_with_chart()
    state["findings"] = [
        Finding(
            id="fnd-001",
            claim="Precio medio del café",
            agent="analyst",
            code_ref="trc-001",
        )
    ]
    return state


@pytest.fixture
def fake_llm(monkeypatch):
    monkeypatch.setattr("tertulia.crew.crew.llm_from_settings", lambda: object())


@pytest.fixture
def fake_to_text(monkeypatch):
    monkeypatch.setattr(
        "tertulia.vision.tool.to_text",
        lambda analysis: f"Análisis completo de {analysis.image_path}",
    )


def test_no_charts_returns_empty_patch():
    state = _state_without_charts()
    assert vision_charts_node(state) == {}


def test_chart_creates_finding_and_trace(monkeypatch, fake_llm, fake_to_text):
    path = "run-1/charts/break_even.png"
    state = _state_with_chart(path)

    monkeypatch.setattr(
        "tertulia.vision.tool.analyse_image",
        lambda image_path, llm, root=None: _analysis(image_path),
    )

    patch = vision_charts_node(state)

    assert len(patch["findings"]) == 2
    assert len(patch["traces"]) == 1
    new_finding = patch["findings"][1]
    assert new_finding.agent == "vision"
    assert new_finding.code_ref == patch["traces"][0].id
    assert new_finding.artifact_paths == [path]
    assert new_finding.claim == "El gráfico muestra un punto de equilibrio de 68 clientes al día"
    new_trace = patch["traces"][0]
    assert new_trace.actor == "vision"
    assert new_trace.tool == "vision.analyse_image"
    assert new_trace.finding_ids == [new_finding.id]
    assert "Análisis completo" in str(new_trace.output)


def test_chart_with_empty_observations_uses_unclear_as_claim(monkeypatch, fake_llm):
    path = "run-1/charts/break_even.png"
    state = _state_with_chart(path)
    analysis = _analysis(path, observations=[], unclear="Imagen borrosa")

    monkeypatch.setattr(
        "tertulia.vision.tool.analyse_image",
        lambda image_path, llm, root=None: analysis,
    )

    patch = vision_charts_node(state)
    assert patch["findings"][1].claim == "Imagen borrosa"


def test_analysis_failure_records_error(monkeypatch, fake_llm):
    path = "run-1/charts/break_even.png"
    state = _state_with_chart(path)

    def _raise(image_path, llm, root=None):
        raise AnalysisFailed("modelo no disponible")

    monkeypatch.setattr("tertulia.vision.tool.analyse_image", _raise)

    patch = vision_charts_node(state)

    assert "findings" not in patch
    assert "traces" not in patch
    assert len(patch["errors"]) == 1
    assert patch["errors"][0].severity == ErrorSeverity.DEGRADABLE
    assert patch["errors"][0].code == TOOL_FAILURE
    assert "break_even.png" in patch["errors"][0].message


def test_rejected_image_records_error(monkeypatch, fake_llm):
    path = "run-1/charts/break_even.png"
    state = _state_with_chart(path)

    def _raise(image_path, llm, root=None):
        raise ImageRejected("not a valid image")

    monkeypatch.setattr("tertulia.vision.tool.analyse_image", _raise)

    patch = vision_charts_node(state)

    assert "findings" not in patch
    assert len(patch["errors"]) == 1
    assert patch["errors"][0].severity == ErrorSeverity.DEGRADABLE
    assert patch["errors"][0].code == TOOL_FAILURE


def test_classified_as_photo_records_error(monkeypatch, fake_llm):
    path = "run-1/charts/break_even.png"
    state = _state_with_chart(path)

    monkeypatch.setattr(
        "tertulia.vision.tool.analyse_image",
        lambda image_path, llm, root=None: _analysis(image_path, kind=ImageKind.PHOTO),
    )

    patch = vision_charts_node(state)

    assert "findings" not in patch
    assert len(patch["errors"]) == 1
    assert "no clasificó" in patch["errors"][0].message.lower()


def test_tokens_exhausted_skips_analysis(monkeypatch):
    from config.settings import settings

    path = "run-1/charts/break_even.png"
    state = _state_with_chart(path)
    state["tokens_used"] = settings.MAX_TOKENS_PER_REPORT

    called = []

    def _must_not_be_called(image_path, llm, root=None):
        called.append(image_path)
        return _analysis(image_path)

    monkeypatch.setattr("tertulia.vision.tool.analyse_image", _must_not_be_called)

    patch = vision_charts_node(state)

    assert called == []
    assert len(patch["errors"]) == 1
    assert patch["errors"][0].severity == ErrorSeverity.FATAL
