"""
Integration test: ``POST /jetson/study-guide/runs/{session_id}/capture-upload``
writes a ``capture`` event to ``interactions.jsonl``.

We exercise the live FastAPI app with ``TestClient`` and:
- monkeypatch ``settings.SESSIONS_DIR`` to ``tmp_path`` so we don't touch
  the real sessions folder;
- replace ``_run_study_grade_upload`` with a no-op so we don't hit the
  vision LLM (deep coverage of capture_feedback is in the unit tests).

We also verify the happy-path ``create_study_run`` emits the initial
``run_started`` + ``question_shown`` events.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_HERE = Path(__file__).resolve()
_jetson_runtime = _HERE.parents[2]
if str(_jetson_runtime) not in sys.path:
    sys.path.insert(0, str(_jetson_runtime))

import jetson_backend  # noqa: E402


_MIN_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16 + b"\xff\xd9"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with isolated SESSIONS_DIR and no real grading thread."""
    jetson_backend._study_runs.clear()
    monkeypatch.setattr(jetson_backend.settings, "SESSIONS_DIR", tmp_path, raising=False)

    # Do NOT actually call the vision LLM; the integration test only cares
    # that the upload endpoint logs a ``capture`` event.
    monkeypatch.setattr(jetson_backend, "_run_study_grade_upload", lambda *a, **k: None)

    # Keep the instructions speaker out of the request path.
    monkeypatch.setattr(jetson_backend, "_speak_study_instructions", lambda: None)

    yield TestClient(jetson_backend.app)
    jetson_backend._study_runs.clear()


def _read_events(tmp_path: Path, session_id: str) -> list[dict]:
    path = tmp_path / session_id / "paper" / "interactions.jsonl"
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def test_create_run_emits_run_started_and_question_shown(
    client: TestClient, tmp_path: Path
) -> None:
    sid = "sess-ints-create"
    resp = client.post(
        "/jetson/study-guide/runs",
        json={
            "session_id": sid,
            "question_text": "Define Bayes' rule.",
            "rubric_items": ["State the formula", "Identify prior/likelihood"],
        },
    )
    assert resp.status_code == 200

    events = _read_events(tmp_path, sid)
    types = [e.get("type") for e in events]
    assert types == ["run_started", "question_shown"]

    started = events[0]
    assert started["session_id"] == sid
    assert started["question_index"] == 0
    assert started["question_specs"][0]["question"] == "Define Bayes' rule."
    assert started["question_specs"][0]["rubric_items"] == [
        "State the formula",
        "Identify prior/likelihood",
    ]

    shown = events[1]
    assert shown["type"] == "question_shown"
    assert shown["question"] == "Define Bayes' rule."
    assert shown["question_index"] == 0


def test_capture_upload_logs_capture_event(
    client: TestClient, tmp_path: Path
) -> None:
    sid = "sess-ints-upload"
    resp = client.post(
        "/jetson/study-guide/runs",
        json={
            "session_id": sid,
            "question_text": "Solve for x.",
            "rubric_items": ["Show work"],
        },
    )
    assert resp.status_code == 200

    resp = client.post(
        f"/jetson/study-guide/runs/{sid}/capture-upload",
        files={"image": ("paper.jpg", _MIN_JPEG, "image/jpeg")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "captured"
    assert body["captureCount"] == 1
    assert body["captureLimit"] == 5

    # The JPEG landed on disk under paper/q0/paper_*.jpg.
    q0_dir = tmp_path / sid / "paper" / "q0"
    jpegs = sorted(q0_dir.glob("paper_*.jpg"))
    assert len(jpegs) == 1
    assert jpegs[0].read_bytes() == _MIN_JPEG

    events = _read_events(tmp_path, sid)
    types = [e.get("type") for e in events]
    # run_started, question_shown at creation + one capture event on upload.
    assert types == ["run_started", "question_shown", "capture"]

    capture_ev = events[-1]
    assert capture_ev["session_id"] == sid
    assert capture_ev["question_index"] == 0
    assert capture_ev["source"] == "upload"
    assert capture_ev["image_filename"] == jpegs[0].name
    assert capture_ev["bytes"] == len(_MIN_JPEG)
    assert capture_ev["image_path"].endswith(jpegs[0].name)


def test_capture_upload_rejects_non_jpeg(client: TestClient, tmp_path: Path) -> None:
    """Smoke: a non-JPEG upload is rejected before any capture event is logged."""
    sid = "sess-ints-bad"
    client.post(
        "/jetson/study-guide/runs",
        json={
            "session_id": sid,
            "question_text": "Q?",
            "rubric_items": ["R"],
        },
    )

    resp = client.post(
        f"/jetson/study-guide/runs/{sid}/capture-upload",
        files={"image": ("not_a_jpeg.bin", b"PNG\x89\x89\x89\x89", "image/jpeg")},
    )
    assert resp.status_code == 400

    events = _read_events(tmp_path, sid)
    types = [e.get("type") for e in events]
    # Creation events only, no capture.
    assert types == ["run_started", "question_shown"]
