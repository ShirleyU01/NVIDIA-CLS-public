"""
Tests for the multi-question teacher feedback builder.

:func:`build_study_teacher_summary_multi` produces the v1
``{summary, flags, action_items}`` shape from a single LLM call that sees
every question, every capture, and the just-built student feedback.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

_HERE = Path(__file__).resolve()
_jetson_runtime = _HERE.parents[2]
if str(_jetson_runtime) not in sys.path:
    sys.path.insert(0, str(_jetson_runtime))

from study_guide.feedback_aggregation import CaptureRecord  # noqa: E402
from study_guide.feedback_contracts import StudyStudentFeedback  # noqa: E402
from study_guide.teacher_summary import (  # noqa: E402
    _build_teacher_prompt_multi,
    build_study_teacher_summary_multi,
)


def _student_fb() -> StudyStudentFeedback:
    return {
        "question": "Study session across 2 questions",
        "high_level_takeaways": ["Solid setup on Q1."],
        "areas_to_improve": ["Units dropped on Q1."],
        "next_steps": ["Practice unit tracking."],
    }


def _captures() -> List[CaptureRecord]:
    return [
        CaptureRecord(
            index=1,
            image_filename="q0/paper_100.jpg",
            feedback_json={"summary": "q1 first attempt"},
            feedback_md="q1 capture 1 markdown",
            question_index=0,
        ),
        CaptureRecord(
            index=2,
            image_filename="q1/paper_200.jpg",
            feedback_json={"summary": "q2 first attempt"},
            feedback_md="q2 capture 1 markdown",
            question_index=1,
        ),
    ]


# ---------------------------------------------------------------------------
# Prompt grounding
# ---------------------------------------------------------------------------


def test_prompt_mentions_every_question_rubric_and_capture_and_student_fb():
    questions = [
        ("Q1 text?", ["rubric A", "rubric B"]),
        ("Q2 text?", ["rubric C"]),
    ]
    system, user = _build_teacher_prompt_multi(
        questions=questions,
        captures=_captures(),
        student_feedback=_student_fb(),
    )

    assert system
    assert "one or more practice problems" in system.lower()

    # Question headers and rubric items.
    assert "=== Question 1 ===" in user
    assert "=== Question 2 ===" in user
    assert "Q1 text?" in user
    assert "Q2 text?" in user
    for r in ("rubric A", "rubric B", "rubric C"):
        assert r in user

    # Capture groupings.
    assert "=== Captures for Question 1 ===" in user
    assert "=== Captures for Question 2 ===" in user
    assert "q0/paper_100.jpg" in user
    assert "q1/paper_200.jpg" in user

    # Student feedback grounding is included verbatim (as JSON).
    assert "Solid setup on Q1." in user
    assert "Units dropped on Q1." in user
    assert "Practice unit tracking." in user

    # Schema pins the teacher v1 contract.
    assert '"summary"' in user
    assert '"flags"' in user
    assert '"action_items"' in user


# ---------------------------------------------------------------------------
# Orchestrator: happy path
# ---------------------------------------------------------------------------


def test_build_returns_parsed_summary_on_happy_path():
    payload = {
        "summary": "Student did well on Q1 and struggled on Q2.",
        "flags": ["unit confusion"],
        "action_items": ["Re-teach unit conversion"],
    }
    captured: List[tuple[str, str]] = []

    def fake_llm(system: str, user: str) -> str:
        captured.append((system, user))
        return json.dumps(payload)

    out = build_study_teacher_summary_multi(
        questions=[("Q1?", []), ("Q2?", [])],
        captures=_captures(),
        student_feedback=_student_fb(),
        llm_complete_fn=fake_llm,
    )
    assert out == payload
    assert len(captured) == 1  # exactly ONE aggregate LLM call


# ---------------------------------------------------------------------------
# Orchestrator: failure modes
# ---------------------------------------------------------------------------


def test_build_falls_back_when_llm_raises():
    def boom(_system: str, _user: str) -> str:
        raise RuntimeError("OpenAI down")

    out = build_study_teacher_summary_multi(
        questions=[("Q1?", []), ("Q2?", [])],
        captures=_captures(),
        student_feedback=_student_fb(),
        llm_complete_fn=boom,
    )
    assert out == {"summary": "", "flags": [], "action_items": []}


def test_build_falls_back_when_llm_returns_garbage():
    def garbage(_system: str, _user: str) -> str:
        return "not JSON"

    out = build_study_teacher_summary_multi(
        questions=[("Q1?", [])],
        captures=[],
        student_feedback=_student_fb(),
        llm_complete_fn=garbage,
    )
    assert out == {"summary": "", "flags": [], "action_items": []}
