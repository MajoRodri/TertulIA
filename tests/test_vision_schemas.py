"""Tests for the vision answer format (src/tertulia/vision/schemas.py)."""

import pytest
from pydantic import ValidationError

from tertulia.vision.vision_schemas import (
    MAX_OBSERVATIONS,
    Category,
    Confidence,
    ImageAnalysis,
    ImageAnswer,
    ImageKind,
    ImageObservation,
)


def _observation(**changes):
    data = {"category": "ambiance", "observation": "Pared de ladrillo visto", "confidence": "high"}
    return {**data, **changes}


def test_a_valid_answer_from_the_model():
    answer = ImageAnswer(
        kind="photo",
        observations=[_observation(), _observation(category="prices", confidence="low")],
        visible_text=["Spoiler Bar"],
        people_visible=False,
    )
    assert answer.kind == ImageKind.PHOTO
    assert answer.observations[1].category == Category.PRICES
    assert answer.observations[1].confidence == Confidence.LOW
    assert answer.unclear is None


def test_an_answer_can_be_built_from_the_json_the_model_returns():
    raw = (
        '{"kind": "chart", "observations": [], "visible_text": [], '
        '"people_visible": false, "unclear": "Imagen demasiado oscura"}'
    )
    answer = ImageAnswer.model_validate_json(raw)
    assert answer.kind == ImageKind.CHART
    assert answer.unclear == "Imagen demasiado oscura"


@pytest.mark.parametrize(
    "changes",
    [
        {"category": "people"},  # not one of our categories
        {"confidence": "0.9"},  # three levels only, no numbers
        {"observation": ""},  # empty
        {"observation": "x" * 301},  # too long: one sentence
    ],
)
def test_bad_observations_are_rejected(changes):
    with pytest.raises(ValidationError):
        ImageObservation(**_observation(**changes))


def test_at_most_eight_observations_per_image():
    too_many = [_observation()] * (MAX_OBSERVATIONS + 1)
    with pytest.raises(ValidationError):
        ImageAnswer(kind="photo", observations=too_many, people_visible=False)


def test_people_visible_must_always_be_answered():
    with pytest.raises(ValidationError):
        ImageAnswer(kind="photo", observations=[])


def test_the_file_and_the_safety_check_are_added_by_our_code():
    answer = ImageAnswer(kind="photo", observations=[_observation()], people_visible=True)
    analysis = ImageAnalysis(**answer.model_dump(), image_path="run-001/uploads/bar.png")
    assert analysis.image_path == "run-001/uploads/bar.png"
    assert analysis.suspicious is False and analysis.injection_patterns == []
    # The model's form has no such fields: it cannot choose the file or the check.
    assert "image_path" not in ImageAnswer.model_fields
    assert "suspicious" not in ImageAnswer.model_fields