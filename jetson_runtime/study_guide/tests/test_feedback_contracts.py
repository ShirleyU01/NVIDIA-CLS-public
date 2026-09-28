"""
Unit tests for the study-mode feedback contracts.

Covers:

- Empty-default builders return well-shaped payloads.
- Markdown ``` and ```json fences are stripped before JSON parsing.
- The three student narrative sections (high_level_takeaways /
  areas_to_improve / next_steps) are parsed as string lists with non-string
  entries silently dropped.
- Missing / malformed fields fall back to safe defaults.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make ``jetson_runtime`` importable as a top-level package root.
_HERE = Path(__file__).resolve()
_jetson_runtime = _HERE.parents[2]
if str(_jetson_runtime) not in sys.path:
    sys.path.insert(0, str(_jetson_runtime))

from study_guide.feedback_contracts import (  # noqa: E402
    empty_study_student_feedback,
    empty_study_teacher_summary,
    parse_study_student_response,
    parse_study_teacher_response,
)


# ---------------------------------------------------------------------------
# Empty defaults
# ---------------------------------------------------------------------------


def test_empty_student_feedback_has_three_empty_sections():
    out = empty_study_student_feedback("Q1?", ["R1", "R2"])

    assert out["question"] == "Q1?"
    assert out["high_level_takeaways"] == []
    assert out["areas_to_improve"] == []
    assert out["next_steps"] == []
    # Legacy keys must be gone so downstream consumers fail loudly if they
    # still expect them.
    assert "steps" not in out
    assert "summary" not in out


def test_empty_student_feedback_accepts_no_rubric_arg():
    out = empty_study_student_feedback("Q?")
    assert out == {
        "question": "Q?",
        "high_level_takeaways": [],
        "areas_to_improve": [],
        "next_steps": [],
    }


def test_empty_teacher_summary_shape():
    out = empty_study_teacher_summary()
    assert out == {"summary": "", "flags": [], "action_items": []}


# ---------------------------------------------------------------------------
# Student response parsing
# ---------------------------------------------------------------------------


def test_parse_student_response_strips_json_fence():
    raw = """```json
{"question": "Q?",
 "high_level_takeaways": ["Got the setup right.", "Solid second attempt."],
 "areas_to_improve": ["Units got dropped in capture 2."],
 "next_steps": ["Redo the block problem with explicit units."]}
```"""
    out = parse_study_student_response(raw, question="Q?")
    assert out["question"] == "Q?"
    assert out["high_level_takeaways"] == [
        "Got the setup right.",
        "Solid second attempt.",
    ]
    assert out["areas_to_improve"] == ["Units got dropped in capture 2."]
    assert out["next_steps"] == ["Redo the block problem with explicit units."]


def test_parse_student_response_strips_plain_fence():
    raw = (
        "```\n"
        '{"high_level_takeaways": ["ok"], "areas_to_improve": [], "next_steps": []}'
        "\n```"
    )
    out = parse_study_student_response(raw, question="Q?")
    assert out["high_level_takeaways"] == ["ok"]
    assert out["areas_to_improve"] == []
    assert out["next_steps"] == []


def test_parse_student_response_falls_back_on_garbage():
    out = parse_study_student_response(
        "I am not JSON at all", question="Q?"
    )
    assert out == empty_study_student_feedback("Q?")


def test_parse_student_response_drops_non_string_entries():
    raw = (
        '{"high_level_takeaways": ["good", "  ", null, 42, "keep"],'
        ' "areas_to_improve": "not a list",'
        ' "next_steps": [true, "do the thing"]}'
    )
    out = parse_study_student_response(raw, question="Q?")
    # Empty strings and null entries are dropped; non-strings coerced to str.
    assert out["high_level_takeaways"] == ["good", "42", "keep"]
    # A non-list value becomes an empty list rather than crashing.
    assert out["areas_to_improve"] == []
    assert out["next_steps"] == ["True", "do the thing"]


def test_parse_student_response_uses_input_question_when_missing():
    raw = (
        '{"high_level_takeaways": [], "areas_to_improve": [], "next_steps": []}'
    )
    out = parse_study_student_response(raw, question="My Question")
    assert out["question"] == "My Question"


def test_parse_student_response_prefers_echoed_question_when_present():
    raw = (
        '{"question": "Echoed question",'
        '"high_level_takeaways": [], "areas_to_improve": [], "next_steps": []}'
    )
    out = parse_study_student_response(raw, question="Fallback")
    assert out["question"] == "Echoed question"


def test_parse_student_response_accepts_legacy_rubric_kwarg():
    # rubric_items is accepted (and ignored) for backwards compatibility with
    # call sites that still pass it.
    raw = '{"high_level_takeaways": ["a"], "areas_to_improve": [], "next_steps": []}'
    out = parse_study_student_response(
        raw, question="Q?", rubric_items=["R1", "R2"]
    )
    assert out["high_level_takeaways"] == ["a"]


# ---------------------------------------------------------------------------
# Teacher response parsing (unchanged contract)
# ---------------------------------------------------------------------------


def test_parse_teacher_response_happy_path():
    raw = (
        '```json\n{"summary": "Strong on derivation, weak on units.",'
        '"flags": ["unit confusion"],'
        '"action_items": ["Re-teach unit conversion", "  ", null, "Practice block 4"]}'
        "\n```"
    )
    out = parse_study_teacher_response(raw)
    assert out["summary"] == "Strong on derivation, weak on units."
    assert out["flags"] == ["unit confusion"]
    # Empty / null entries are dropped from list fields.
    assert out["action_items"] == ["Re-teach unit conversion", "Practice block 4"]


def test_parse_teacher_response_missing_keys_default_to_empty():
    out = parse_study_teacher_response('{"summary": "ok"}')
    assert out == {"summary": "ok", "flags": [], "action_items": []}


def test_parse_teacher_response_garbage_falls_back():
    out = parse_study_teacher_response("not json")
    assert out == empty_study_teacher_summary()


def test_parse_teacher_response_non_object_falls_back():
    out = parse_study_teacher_response("[1, 2, 3]")
    assert out == empty_study_teacher_summary()
