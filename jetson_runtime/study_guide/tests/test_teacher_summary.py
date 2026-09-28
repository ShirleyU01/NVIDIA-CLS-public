"""
Tests for :func:`build_study_teacher_summary`.
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
from study_guide.teacher_summary import (  # noqa: E402
    _build_teacher_prompt,
    build_study_teacher_summary,
)


def _captures() -> List[CaptureRecord]:
    return [
        CaptureRecord(
            index=1,
            image_filename="paper_1.jpg",
            feedback_json={"summary": "first try, off"},
            feedback_md="md1",
        ),
        CaptureRecord(
            index=2,
            image_filename="paper_2.jpg",
            feedback_json={"summary": "second try, on track"},
            feedback_md="md2",
        ),
    ]


def _student_feedback() -> dict:
    return {
        "question": "Q?",
        "summary": "Solid recovery on second try.",
        "steps": [
            {"rubric_item": "R1", "status": "correct", "evidence": "see capture 2",
             "feedback": "Right.", "next_step": ""},
            {"rubric_item": "R2", "status": "partial", "evidence": "capture 1",
             "feedback": "Almost.", "next_step": "Check units."},
        ],
    }


# ---------------------------------------------------------------------------
# Prompt grounding
# ---------------------------------------------------------------------------


def test_prompt_mentions_question_rubric_captures_and_student_feedback():
    rubric = ["R1", "R2"]
    system, user = _build_teacher_prompt(
        question_text="What is the acceleration?",
        rubric_items=rubric,
        captures=_captures(),
        student_feedback=_student_feedback(),  # type: ignore[arg-type]
    )

    assert "instructor" in system.lower()
    assert "What is the acceleration?" in user
    for r in rubric:
        assert r in user
    assert "paper_1.jpg" in user and "paper_2.jpg" in user
    # Student feedback must be embedded so the teacher prompt is grounded.
    assert "Solid recovery on second try." in user
    assert '"flags"' in user and '"action_items"' in user


# ---------------------------------------------------------------------------
# Orchestrator: happy path + failure modes
# ---------------------------------------------------------------------------


def test_build_returns_parsed_summary_on_happy_path():
    payload = {
        "summary": "Strong derivation, weak units.",
        "flags": ["unit confusion"],
        "action_items": ["Re-teach unit conversion"],
    }
    captured: List[tuple[str, str]] = []

    def fake_llm(system: str, user: str) -> str:
        captured.append((system, user))
        return json.dumps(payload)

    out = build_study_teacher_summary(
        question_text="Q?",
        rubric_items=["R1", "R2"],
        captures=_captures(),
        student_feedback=_student_feedback(),  # type: ignore[arg-type]
        llm_complete_fn=fake_llm,
    )
    assert out["summary"] == "Strong derivation, weak units."
    assert out["flags"] == ["unit confusion"]
    assert out["action_items"] == ["Re-teach unit conversion"]
    assert len(captured) == 1


def test_build_falls_back_when_llm_raises():
    def boom(_system: str, _user: str) -> str:
        raise RuntimeError("nope")

    out = build_study_teacher_summary(
        question_text="Q?",
        rubric_items=["R1"],
        captures=_captures(),
        student_feedback=_student_feedback(),  # type: ignore[arg-type]
        llm_complete_fn=boom,
    )
    assert out == {"summary": "", "flags": [], "action_items": []}


def test_build_falls_back_on_garbage_llm_output():
    def garbage(_system: str, _user: str) -> str:
        return "totally not JSON"

    out = build_study_teacher_summary(
        question_text="Q?",
        rubric_items=[],
        captures=[],
        student_feedback={"question": "", "summary": "", "steps": []},  # type: ignore[arg-type]
        llm_complete_fn=garbage,
    )
    assert out["summary"] == "" and out["flags"] == [] and out["action_items"] == []
