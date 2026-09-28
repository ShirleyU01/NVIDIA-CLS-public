"""
Tests for the multi-question student feedback builder.

:func:`build_study_student_feedback_multi` produces the *same* v1 three-bucket
shape as the single-question builder but from one aggregate LLM call that
sees every question and every capture. These tests exercise:

- prompt grounding: every question text, every rubric item, and every
  capture filename shows up in the user prompt, under the right
  ``=== Question k ===`` / ``=== Captures for Question k ===`` headers;
- happy-path JSON is parsed into the three-section contract;
- LLM errors fall back to a well-shaped empty payload.
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
from study_guide.student_summary import (  # noqa: E402
    _build_student_prompt_multi,
    build_study_student_feedback_multi,
)


def _captures() -> List[CaptureRecord]:
    """Two captures for Q1, one for Q2, one orphaned under Q5."""
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
            image_filename="q0/paper_200.jpg",
            feedback_json={"summary": "q1 second attempt"},
            feedback_md="q1 capture 2 markdown",
            question_index=0,
        ),
        CaptureRecord(
            index=3,
            image_filename="q1/paper_300.jpg",
            feedback_json={"summary": "q2 first attempt"},
            feedback_md="q2 capture 1 markdown",
            question_index=1,
        ),
        CaptureRecord(
            index=4,
            image_filename="q5/paper_400.jpg",
            feedback_json={"summary": "orphaned capture"},
            feedback_md="unlinked markdown",
            question_index=5,
        ),
    ]


# ---------------------------------------------------------------------------
# Prompt grounding
# ---------------------------------------------------------------------------


def test_prompt_mentions_every_question_rubric_and_capture():
    questions = [
        ("What is the acceleration?", ["State Newton's 2nd law", "Apply F=ma"]),
        ("Define a random variable.", ["Name the probability space"]),
    ]
    system, user = _build_student_prompt_multi(
        questions=questions,
        captures=_captures(),
    )

    assert system  # non-empty multi system prompt
    assert "one or more practice problems" in system.lower()

    # Question headers + rubric items are present in order.
    assert "=== Question 1 ===" in user
    assert "=== Question 2 ===" in user
    assert "What is the acceleration?" in user
    assert "Define a random variable." in user
    for rubric in ("State Newton's 2nd law", "Apply F=ma", "Name the probability space"):
        assert rubric in user

    # Capture-group headers map 1:1 to questions.
    assert "=== Captures for Question 1 ===" in user
    assert "=== Captures for Question 2 ===" in user

    # Every capture filename + every per-capture markdown shows up.
    for filename in (
        "q0/paper_100.jpg",
        "q0/paper_200.jpg",
        "q1/paper_300.jpg",
        "q5/paper_400.jpg",
    ):
        assert filename in user
    for md in (
        "q1 capture 1 markdown",
        "q1 capture 2 markdown",
        "q2 capture 1 markdown",
        "unlinked markdown",
    ):
        assert md in user

    # Captures that don't correspond to any declared question fall under
    # an "Unlinked captures" block so the LLM still sees them.
    assert "=== Unlinked captures ===" in user

    # Schema instructions pin the three-section output contract.
    assert '"high_level_takeaways"' in user
    assert '"areas_to_improve"' in user
    assert '"next_steps"' in user


def test_prompt_handles_empty_inputs():
    system, user = _build_student_prompt_multi(questions=[], captures=[])
    assert system
    assert "(no questions)" in user
    assert "no captures were taken" in user


def test_prompt_puts_questions_and_captures_in_declared_order():
    questions = [
        ("Alpha", ["a1"]),
        ("Beta", ["b1"]),
    ]
    captures = [
        CaptureRecord(
            index=1,
            image_filename="beta_cap.jpg",
            feedback_md="BETA-MD",
            question_index=1,
        ),
        CaptureRecord(
            index=2,
            image_filename="alpha_cap.jpg",
            feedback_md="ALPHA-MD",
            question_index=0,
        ),
    ]
    _system, user = _build_student_prompt_multi(questions=questions, captures=captures)

    alpha_header = user.index("=== Captures for Question 1 ===")
    beta_header = user.index("=== Captures for Question 2 ===")
    assert alpha_header < beta_header
    # Each capture appears under the header matching its question_index.
    alpha_block = user[alpha_header:beta_header]
    beta_block = user[beta_header:]
    assert "alpha_cap.jpg" in alpha_block and "ALPHA-MD" in alpha_block
    assert "beta_cap.jpg" in beta_block and "BETA-MD" in beta_block


# ---------------------------------------------------------------------------
# Orchestrator: happy path
# ---------------------------------------------------------------------------


def test_build_returns_parsed_feedback_on_happy_path():
    payload = {
        "question": "Study session across 2 questions",
        "high_level_takeaways": [
            "Set up the free-body diagram correctly on Q1.",
            "Defined the probability space on Q2.",
        ],
        "areas_to_improve": ["Units dropped on Q1 capture 1."],
        "next_steps": ["Redo Q1 writing units at every step."],
    }
    captured: List[tuple[str, str]] = []

    def fake_llm(system: str, user: str) -> str:
        captured.append((system, user))
        return json.dumps(payload)

    out = build_study_student_feedback_multi(
        questions=[("Q1?", ["r1"]), ("Q2?", ["r2"])],
        captures=_captures(),
        llm_complete_fn=fake_llm,
    )
    assert out["question"] == "Study session across 2 questions"
    assert out["high_level_takeaways"] == payload["high_level_takeaways"]
    assert out["areas_to_improve"] == payload["areas_to_improve"]
    assert out["next_steps"] == payload["next_steps"]
    assert len(captured) == 1  # exactly ONE aggregate LLM call


# ---------------------------------------------------------------------------
# Orchestrator: failure modes
# ---------------------------------------------------------------------------


def test_build_falls_back_when_llm_raises():
    def boom(_system: str, _user: str) -> str:
        raise RuntimeError("OpenAI down")

    out = build_study_student_feedback_multi(
        questions=[("Q1?", []), ("Q2?", [])],
        captures=_captures(),
        llm_complete_fn=boom,
    )
    assert out == {
        "question": "",
        "high_level_takeaways": [],
        "areas_to_improve": [],
        "next_steps": [],
    }


def test_build_falls_back_when_llm_returns_garbage():
    def garbage(_system: str, _user: str) -> str:
        return "totally not JSON"

    out = build_study_student_feedback_multi(
        questions=[("Q1?", [])],
        captures=[],
        llm_complete_fn=garbage,
    )
    assert out["high_level_takeaways"] == []
    assert out["areas_to_improve"] == []
    assert out["next_steps"] == []
