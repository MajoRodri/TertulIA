"""Tests del módulo de persistencia de trazas (Issue #16).

Los tests no escriben en ``trazas/`` del repo: monkeypatchean ``TRAZAS_DIR``
a un ``tmp_path`` de pytest.
"""

import json
from datetime import UTC, datetime

import pytest

from tertulia.schemas import TraceEntry
from tertulia.trazas import store
from tertulia.trazas.store import save_traces


def _trace(id: str, **overrides) -> TraceEntry:
    """Una TraceEntry mínima pero válida, para tests."""
    data = {
        "id": id,
        "timestamp": datetime.now(UTC),
        "actor": "human",
        "tool": "ui.approve",
        "inputs": {"human_approved": True},
        "output": {"decision": "approved"},
    }
    return TraceEntry(**{**data, **overrides})


@pytest.fixture
def tmp_trazas(tmp_path, monkeypatch):
    """Redirige TRAZAS_DIR a un directorio temporal por test."""
    monkeypatch.setattr(store, "TRAZAS_DIR", tmp_path)
    return tmp_path


def test_an_empty_list_writes_an_empty_file(tmp_trazas):
    path = save_traces([], "job-abc123")
    assert path == tmp_trazas / "job-abc123" / "traces.jsonl"
    assert path.read_text(encoding="utf-8") == ""


def test_one_trace_round_trips_through_json(tmp_trazas):
    original = _trace("trc-001")
    path = save_traces([original], "job-abc123")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = TraceEntry.model_validate_json(lines[0])
    assert parsed.id == original.id
    assert parsed.actor == original.actor
    assert parsed.tool == original.tool


def test_three_traces_keep_their_order(tmp_trazas):
    traces = [_trace(f"trc-{i:03d}") for i in (1, 2, 3)]
    path = save_traces(traces, "job-abc123")
    ids = [
        json.loads(line)["id"]
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert ids == ["trc-001", "trc-002", "trc-003"]


def test_a_trace_with_an_error_is_serialised(tmp_trazas):
    original = _trace("trc-001", error="tool failed")
    path = save_traces([original], "job-abc123")
    parsed = TraceEntry.model_validate_json(
        path.read_text(encoding="utf-8").strip()
    )
    assert parsed.error == "tool failed"


@pytest.mark.parametrize(
    "bad_id",
    ["", "../etc", "job/123", "job\\123", "job.123", "job 123"],
)
def test_invalid_job_id_is_rejected(bad_id, tmp_trazas):
    with pytest.raises(ValueError, match="invalid job_id"):
        save_traces([], bad_id)


def test_saving_twice_overwrites_the_same_file(tmp_trazas):
    path = save_traces([_trace("trc-001")], "job-abc123")
    save_traces([_trace("trc-001"), _trace("trc-002")], "job-abc123")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
