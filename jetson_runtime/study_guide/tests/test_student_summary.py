"""
Tests for :func:`build_study_student_feedback`.

We never call the real LLM; instead we inject a tiny ``llm_complete_fn``
stub that records the prompts it was given, and that lets us assert:

- the prompt mentions the question, every rubric item, and every capture's
  in-session feedback (prompt grounding - this is what makes the summary
  "based on the per-capture feedback");
- happy-path JSON is parsed into the three-section contract;
- LLM errors fall back to :func:`empty_study_student_feedback`;
- the orchestrator passes ``(system, user)`` to the LLM in that order.
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
    _build_student_prompt,
    build_study_student_feedback,
)


def _captures() -> List[CaptureRecord]:
    return [
        CaptureRecord(
            index=1,
            image_filename="paper_100.jpg",
            feedback_json={"summary": "first attempt OK"},
            feedback_md="capture 1 markdown",
        ),
        CaptureRecord(
            index=2,
            image_filename="paper_200.jpg",
            feedback_json={"summary": "got it on the second try"},
            feedback_md="capture 2 markdown",
        ),
    ]


# ---------------------------------------------------------------------------
# Prompt grounding
# ---------------------------------------------------------------------------


def test_prompt_mentions_question_rubric_and_each_capture():
    rubric = ["State Newton's 2nd law", "Apply F=ma"]
    system, user = _build_student_prompt(
        question_text="What is the acceleration?",
        rubric_items=rubric,
        captures=_captures(),
    )

    assert system  # non-empty system prompt
    assert "What is the acceleration?" in user
    for r in rubric:
        assert r in user
    # Per-capture grounding: both the image filename and its in-session
    # feedback markdown / JSON must show up in the user prompt so the LLM
    # is actually summarizing the in-session feedback.
    assert "paper_100.jpg" in user
    assert "paper_200.jpg" in user
    assert "capture 1 markdown" in user
    assert "capture 2 markdown" in user
    assert "first attempt OK" in user
    assert "got it on the second try" in user
    # Schema instructions pin the three-section output contract.
    assert '"high_level_takeaways"' in user
    assert '"areas_to_improve"' in user
    assert '"next_steps"' in user


def test_prompt_system_describes_three_section_summarization():
    system, _user = _build_student_prompt(
        question_text="Q?", rubric_items=[], captures=[]
    )
    lower = system.lower()
    assert "summariz" in lower  # "summarize" / "summarizing"
    assert "high-level takeaways" in lower
    assert "areas to improve" in lower
    assert "next steps" in lower


def test_prompt_handles_no_rubric_or_captures_without_crashing():
    _system, user = _build_student_prompt(
        question_text="Q?", rubric_items=[], captures=[]
    )
    assert "Q?" in user
    assert "no rubric items" in user
    assert "no captures were taken" in user


# ---------------------------------------------------------------------------
# Orchestrator: happy path
# ---------------------------------------------------------------------------


def test_build_returns_parsed_feedback_on_happy_path():
    rubric = ["R1", "R2"]
    payload = {
        "question": "Q?",
        "high_level_takeaways": [
            "Correct setup across both captures.",
            "Clear improvement between capture 1 and capture 2.",
        ],
        "areas_to_improve": ["Units were dropped in capture 1."],
        "next_steps": ["Redo the problem writing units at every step."],
    }
    captured: List[tuple[str, str]] = []

    def fake_llm(system: str, user: str) -> str:
        captured.append((system, user))
        return json.dumps(payload)

    out = build_study_student_feedback(
        question_text="Q?",
        rubric_items=rubric,
        captures=_captures(),
        llm_complete_fn=fake_llm,
    )
    assert out["question"] == "Q?"
    assert out["high_level_takeaways"] == [
        "Correct setup across both captures.",
        "Clear improvement between capture 1 and capture 2.",
    ]
    assert out["areas_to_improve"] == ["Units were dropped in capture 1."]
    assert out["next_steps"] == ["Redo the problem writing units at every step."]
    # System prompt always passed first.
    assert len(captured) == 1
    sys_arg, user_arg = captured[0]
    assert "teaching assistant" in sys_arg.lower()
    assert "Q?" in user_arg


# ---------------------------------------------------------------------------
# Orchestrator: failure modes
# ---------------------------------------------------------------------------


def test_build_falls_back_when_llm_raises():
    def boom(_system: str, _user: str) -> str:
        raise RuntimeError("OpenAI down")

    out = build_study_student_feedback(
        question_text="Q?",
        rubric_items=["R1", "R2"],
        captures=_captures(),
        llm_complete_fn=boom,
    )
    assert out == {
        "question": "Q?",
        "high_level_takeaways": [],
        "areas_to_improve": [],
        "next_steps": [],
    }


def test_build_falls_back_when_llm_returns_garbage():
    def garbage(_system: str, _user: str) -> str:
        return "totally not JSON"

    out = build_study_student_feedback(
        question_text="Q?",
        rubric_items=["R1"],
        captures=[],
        llm_complete_fn=garbage,
    )
    assert out["high_level_takeaways"] == []
    assert out["areas_to_improve"] == []
    assert out["next_steps"] == []


def test_build_handles_non_string_llm_return():
    def returns_int(_system: str, _user: str):
        return 42  # type: ignore[return-value]

    out = build_study_student_feedback(
        question_text="Q?",
        rubric_items=["R1"],
        captures=[],
        llm_complete_fn=returns_int,  # type: ignore[arg-type]
    )
    # Non-string return is coerced to a string, which is still invalid JSON
    # so we fall back to the empty three-section payload.
    assert out["question"] == "Q?"
    assert out["high_level_takeaways"] == []
