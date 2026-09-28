"""
Unit tests for :mod:`study_guide.session_log`.

Scope:
- Happy path: every supported event type round-trips through JSONL and the
  ``finalize`` rollup has the expected top-level shape.
- Concurrency: many threads hammering ``log_event`` never produce a line
  that fails to parse or gets interleaved.
- Tolerance: missing dir / corrupt line / non-JSON-serializable payload all
  behave predictably.
"""

from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_HERE = Path(__file__).resolve()
_jetson_runtime = _HERE.parents[2]
if str(_jetson_runtime) not in sys.path:
    sys.path.insert(0, str(_jetson_runtime))

from study_guide import session_log  # noqa: E402


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_full_run_roundtrip(tmp_path: Path) -> None:
    """
    Simulate a complete study-run timeline using only ``session_log``:
    run_started -> question_shown -> capture -> capture_feedback ->
    ama_turn(user) -> ama_turn(assistant) -> helper_action -> run_ended ->
    finalize.

    Asserts:
    - JSONL has exactly the events in input order.
    - Every line parses independently.
    - ``interactions.json`` is well-shaped and ``events`` matches the JSONL.
    """
    session_dir = tmp_path / "sess-happy" / "paper"

    events_in: List[Dict[str, Any]] = [
        {
            "ts": 1.0,
            "type": "run_started",
            "session_id": "sess-happy",
            "question_specs": [
                {"qid": "q1", "question": "What is 2+2?", "rubric_items": ["R1"]},
                {"qid": "q2", "question": "Define MLE", "rubric_items": ["R2", "R3"]},
            ],
        },
        {
            "ts": 1.1,
            "type": "question_shown",
            "question_index": 0,
            "question": "What is 2+2?",
            "rubric_items": ["R1"],
        },
        {
            "ts": 2.0,
            "type": "capture",
            "question_index": 0,
            "source": "upload",
            "image_path": "/tmp/p/q0/paper_1.jpg",
            "image_filename": "paper_1.jpg",
            "bytes": 42,
        },
        {
            "ts": 2.5,
            "type": "capture_feedback",
            "question_index": 0,
            "image_filename": "paper_1.jpg",
            "feedback_json": {"verdict": "Correct", "notes": "Right answer."},
            "feedback_md": "- Correct.\n",
        },
        {
            "ts": 3.0,
            "type": "ama_turn",
            "question_index": 0,
            "role": "user",
            "content": "Why does this work?",
        },
        {
            "ts": 3.2,
            "type": "ama_turn",
            "question_index": 0,
            "role": "assistant",
            "content": "Because addition is associative.",
            "model": "gpt-5.4-mini",
        },
        {
            "ts": 4.0,
            "type": "helper_action",
            "question_index": 0,
            "action": "question",
            "student_text": "What if I used subtraction?",
            "reply_md": "Then you would get 0.",
        },
        {
            "ts": 5.0,
            "type": "run_ended",
            "question_count": 2,
        },
    ]

    for ev in events_in:
        session_log.log_event(session_dir, ev)

    jsonl = (session_dir / "interactions.jsonl").read_text(encoding="utf-8")
    lines = [l for l in jsonl.splitlines() if l.strip()]
    assert len(lines) == len(events_in)
    for raw_line, original in zip(lines, events_in):
        parsed = json.loads(raw_line)  # every line must parse independently
        assert parsed["type"] == original["type"]
        assert parsed["ts"] == original["ts"]

    read_back = session_log.read_events(session_dir)
    assert read_back == events_in

    extra = {
        "study_feedback": {
            "high_level_takeaways": ["You showed you understand the basics."],
            "areas_to_improve": [],
            "next_steps": ["You should try a harder variant."],
        },
        "study_teacher_summary": {
            "summary": "The student had the right idea.",
            "flags": [],
            "action_items": ["Move on to the next unit."],
        },
    }
    out = session_log.finalize(session_dir, extra=extra)

    assert out == session_dir / "interactions.json"
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["session_id"] == "sess-happy"
    assert payload["summary"] == extra
    assert payload["events"] == events_in


# ---------------------------------------------------------------------------
# Edge case 1: concurrent multi-thread writes
# ---------------------------------------------------------------------------


def test_concurrent_log_event_never_corrupts_lines(tmp_path: Path) -> None:
    """
    Eight threads each append 50 distinct events. We then assert:
    - The file has exactly 8*50 = 400 non-empty lines.
    - Every line parses independently (no interleaving / partial writes).
    - The multiset of (thread_id, seq) pairs matches the input.
    """
    session_dir = tmp_path / "sess-concurrent" / "paper"

    threads_count = 8
    per_thread = 50

    def worker(tid: int) -> None:
        for seq in range(per_thread):
            session_log.log_event(
                session_dir,
                {
                    "type": "probe",
                    "thread_id": tid,
                    "seq": seq,
                    "payload": "x" * 200,  # wider than typical, stresses atomicity
                },
            )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(threads_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    text = (session_dir / "interactions.jsonl").read_text(encoding="utf-8")
    lines = [l for l in text.splitlines() if l.strip()]
    assert len(lines) == threads_count * per_thread

    seen: set[tuple[int, int]] = set()
    for raw_line in lines:
        parsed = json.loads(raw_line)  # would raise if the line were torn
        assert parsed["type"] == "probe"
        key = (parsed["thread_id"], parsed["seq"])
        assert key not in seen, f"duplicate event detected: {key}"
        seen.add(key)

    expected = {(t, s) for t in range(threads_count) for s in range(per_thread)}
    assert seen == expected


# ---------------------------------------------------------------------------
# Edge case 2: tolerant reads / missing dir / non-JSON-safe payloads
# ---------------------------------------------------------------------------


def test_read_events_missing_dir_returns_empty(tmp_path: Path) -> None:
    """``read_events`` on a session dir that doesn't exist is a soft []."""
    assert session_log.read_events(tmp_path / "no-such-session" / "paper") == []


def test_read_events_skips_corrupt_line(tmp_path: Path) -> None:
    """One garbage line between two valid events is skipped, not fatal."""
    session_dir = tmp_path / "sess-corrupt" / "paper"
    session_dir.mkdir(parents=True, exist_ok=True)

    good_a = {"ts": 1.0, "type": "run_started", "session_id": "sess-corrupt"}
    good_b = {"ts": 2.0, "type": "question_shown", "question_index": 0}

    path = session_dir / "interactions.jsonl"
    path.write_text(
        json.dumps(good_a) + "\n"
        + "{this is not json, oh no\n"
        + json.dumps(good_b) + "\n",
        encoding="utf-8",
    )

    events = session_log.read_events(session_dir)
    assert events == [good_a, good_b]


def test_log_event_serializes_path_and_datetime(tmp_path: Path) -> None:
    """
    A payload that contains a ``Path`` and a ``datetime`` must still round
    trip via ``default=str`` without raising. We don't require the exact
    string form - only that the values come back as strings we can read.
    """
    session_dir = tmp_path / "sess-exotic" / "paper"

    img_path = tmp_path / "frames" / "paper_1.jpg"
    now = datetime(2026, 4, 21, 12, 0, 0, tzinfo=timezone.utc)

    session_log.log_event(
        session_dir,
        {
            "ts": 99.0,
            "type": "capture",
            "question_index": 0,
            "image_path": img_path,  # Path
            "taken_at": now,  # datetime
        },
    )

    events = session_log.read_events(session_dir)
    assert len(events) == 1
    ev = events[0]
    assert ev["type"] == "capture"
    assert ev["question_index"] == 0
    # Path and datetime coerced via default=str.
    assert isinstance(ev["image_path"], str)
    assert ev["image_path"].endswith("paper_1.jpg")
    assert isinstance(ev["taken_at"], str)
    assert "2026-04-21" in ev["taken_at"]


def test_finalize_creates_dir_when_missing(tmp_path: Path) -> None:
    """
    ``finalize`` on a never-logged session still produces a well-shaped
    rollup file with an empty events list and empty summary.
    """
    session_dir = tmp_path / "sess-empty" / "paper"
    assert not session_dir.exists()

    out = session_log.finalize(session_dir)
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload == {
        "session_id": "sess-empty",
        "events": [],
        "summary": {},
    }
