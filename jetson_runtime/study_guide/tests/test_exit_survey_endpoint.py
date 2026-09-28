"""
Tests for ``POST /jetson/study-guide/runs/{session_id}/survey``.

We exercise the live FastAPI ``app`` with ``TestClient`` and:

- redirect ``settings.SESSIONS_DIR`` to ``tmp_path`` so disk writes land
  there;
- clear ``_study_runs`` between tests so we can exercise both the
  "runtime still present" and "runtime already cleared" branches of the
  endpoint.

The endpoint is deliberately independent of any live ``_StudyRuntime``:
surveys can arrive after ``/end`` has popped the runtime, so we verify
the happy path works with and without one.
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
from jetson_backend import _StudyRuntime  # noqa: E402


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    jetson_backend._study_runs.clear()
    monkeypatch.setattr(jetson_backend.settings, "SESSIONS_DIR", tmp_path, raising=False)
    yield TestClient(jetson_backend.app)
    jetson_backend._study_runs.clear()


def _seed_runtime(session_id: str) -> _StudyRuntime:
    runtime = _StudyRuntime(
        session_id=session_id,
        status="idle",
        question_text="Q?",
        rubric_items=["R"],
    )
    jetson_backend._study_runs[session_id] = runtime
    return runtime


def _read_jsonl(tmp_path: Path, session_id: str) -> list[dict]:
    path = tmp_path / session_id / "paper" / "interactions.jsonl"
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_survey_happy_path_writes_disk_and_logs_event(
    client: TestClient, tmp_path: Path
) -> None:
    sid = "sess-happy"
    _seed_runtime(sid)

    body = {
        "helpfulness": 4,
        "ease_of_use": 5,
        "question_difficulty": 3,
        "would_use_again": True,
        "liked": "The instant feedback was great.",
        "disliked": "Nothing really.",
        "improvements": "More practice problems.",
        "response_feedback": "The responses were specific enough and did not feel vague.",
    }
    resp = client.post(f"/jetson/study-guide/runs/{sid}/survey", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "ok"}

    # survey.json matches the submitted fields.
    survey_path = tmp_path / sid / "paper" / "survey.json"
    assert survey_path.exists()
    on_disk = json.loads(survey_path.read_text(encoding="utf-8"))
    assert on_disk["session_id"] == sid
    assert on_disk["helpfulness"] == 4
    assert on_disk["ease_of_use"] == 5
    assert on_disk["question_difficulty"] == 3
    assert on_disk["would_use_again"] is True
    assert on_disk["liked"] == body["liked"]
    assert on_disk["disliked"] == body["disliked"]
    assert on_disk["improvements"] == body["improvements"]
    assert on_disk["response_feedback"] == body["response_feedback"]
    assert isinstance(on_disk["submitted_at"], str) and on_disk["submitted_at"]

    # interactions.jsonl gained a survey_submitted event carrying the
    # runtime-provided question_index because a runtime was present.
    events = _read_jsonl(tmp_path, sid)
    survey_events = [e for e in events if e.get("type") == "survey_submitted"]
    assert len(survey_events) == 1
    ev = survey_events[0]
    assert ev["session_id"] == sid
    assert ev["helpfulness"] == 4
    assert ev["ease_of_use"] == 5
    assert ev["question_difficulty"] == 3
    assert ev["would_use_again"] is True
    assert ev["liked"] == body["liked"]
    assert ev["response_feedback"] == body["response_feedback"]
    assert ev["question_index"] == 0


# ---------------------------------------------------------------------------
# Partial submit
# ---------------------------------------------------------------------------


def test_survey_partial_submit_defaults_missing_fields(
    client: TestClient, tmp_path: Path
) -> None:
    sid = "sess-partial"
    _seed_runtime(sid)

    resp = client.post(
        f"/jetson/study-guide/runs/{sid}/survey",
        json={"helpfulness": 3},
    )
    assert resp.status_code == 200

    on_disk = json.loads(
        (tmp_path / sid / "paper" / "survey.json").read_text(encoding="utf-8")
    )
    assert on_disk["helpfulness"] == 3
    assert on_disk["ease_of_use"] is None
    assert on_disk["question_difficulty"] is None
    assert on_disk["would_use_again"] is None
    assert on_disk["liked"] == ""
    assert on_disk["disliked"] == ""
    assert on_disk["improvements"] == ""
    assert on_disk["response_feedback"] == ""


# ---------------------------------------------------------------------------
# Out-of-range ratings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_payload",
    [
        {"helpfulness": 0},
        {"helpfulness": 7},
        {"ease_of_use": -1},
        {"ease_of_use": 6},
        {"question_difficulty": 0},
        {"question_difficulty": 9},
    ],
)
def test_survey_rejects_out_of_range_likert(
    client: TestClient, tmp_path: Path, bad_payload: dict
) -> None:
    sid = "sess-bad"
    _seed_runtime(sid)

    resp = client.post(f"/jetson/study-guide/runs/{sid}/survey", json=bad_payload)
    assert resp.status_code == 400
    assert "between 1 and 5" in resp.json()["detail"]

    # Nothing written on validation failure.
    assert not (tmp_path / sid / "paper" / "survey.json").exists()
    assert not (tmp_path / sid / "paper" / "interactions.jsonl").exists()


# ---------------------------------------------------------------------------
# Runtime-already-cleared (survey arrives after /end popped the runtime)
# ---------------------------------------------------------------------------


def test_survey_succeeds_when_runtime_is_gone(
    client: TestClient, tmp_path: Path
) -> None:
    sid = "sess-no-runtime"
    # Deliberately do NOT seed a runtime. Simulates the user landing on the
    # survey page after the client has already torn down / navigated past
    # the study run in memory.
    assert sid not in jetson_backend._study_runs

    resp = client.post(
        f"/jetson/study-guide/runs/{sid}/survey",
        json={
            "helpfulness": 2,
            "ease_of_use": 4,
            "question_difficulty": 5,
            "would_use_again": False,
            "liked": "",
            "disliked": "Some UI friction",
            "improvements": "",
            "response_feedback": "The response was a little too vague for the mistake I made.",
        },
    )
    assert resp.status_code == 200

    # File still written under the right path.
    on_disk = json.loads(
        (tmp_path / sid / "paper" / "survey.json").read_text(encoding="utf-8")
    )
    assert on_disk["helpfulness"] == 2
    assert on_disk["question_difficulty"] == 5
    assert on_disk["would_use_again"] is False
    assert on_disk["disliked"] == "Some UI friction"
    assert on_disk["response_feedback"] == "The response was a little too vague for the mistake I made."

    # Event still logged, with session_id but without question_index because
    # no runtime was available to supply it.
    events = _read_jsonl(tmp_path, sid)
    survey_events = [e for e in events if e.get("type") == "survey_submitted"]
    assert len(survey_events) == 1
    ev = survey_events[0]
    assert ev["session_id"] == sid
    assert ev["question_difficulty"] == 5
    assert ev["would_use_again"] is False
    assert ev["response_feedback"] == "The response was a little too vague for the mistake I made."
    assert "question_index" not in ev
