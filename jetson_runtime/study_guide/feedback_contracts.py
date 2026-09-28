"""
Study-mode post-session feedback contracts.

These data shapes are produced on the Jetson when a student ends a study run,
written to disk as ``study_feedback.json``, and then POSTed to the central
backend as session artifacts. Both the student review page and the teacher
session-detail page read the same shapes back from central.

Two contracts live here:

- :data:`StudyStudentFeedback` - three standardized narrative sections
  (high-level takeaways, areas to improve, next steps) summarizing the
  student's in-session per-capture feedback.
- :data:`StudyTeacherSummary`  - short narrative + flags + action items for the
  teacher.

Every helper in this module is intentionally defensive: an LLM that returns
malformed JSON (or no JSON at all) must never crash the pipeline. The parsers
fall back to "empty default" shapes so downstream UIs always have something
well-formed to render.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, List, Optional, TypedDict


# ---------------------------------------------------------------------------
# TypedDict contracts
# ---------------------------------------------------------------------------


class StudyStudentFeedback(TypedDict):
    """Top-level per-question feedback the student sees on the review page.

    The post-session report is a summarization of the in-session per-capture
    feedback, organized into three standardized bulleted sections.
    """

    question: str  # the (one) study question
    high_level_takeaways: List[str]  # short bullets, 1 sentence each
    areas_to_improve: List[str]  # short bullets, 1 sentence each
    next_steps: List[str]  # short bullets, concrete actionable advice


class StudyTeacherSummary(TypedDict):
    """Short instructor-facing roll-up for the teacher session-detail page."""

    summary: str  # 2-3 sentence narrative for the instructor
    flags: List[str]  # short risk/struggle bullets
    action_items: List[str]  # concrete next steps for the instructor


# ---------------------------------------------------------------------------
# Empty defaults (fallback paths)
# ---------------------------------------------------------------------------


def empty_study_student_feedback(
    question: str, rubric_items: Optional[Iterable[str]] = None
) -> StudyStudentFeedback:
    """Build a "no feedback available" student payload with empty sections.

    ``rubric_items`` is accepted (and ignored) so call sites that still pass
    the rubric for historical reasons keep working without churn.
    """
    del rubric_items  # no longer used; accepted for signature compatibility
    return {
        "question": str(question or ""),
        "high_level_takeaways": [],
        "areas_to_improve": [],
        "next_steps": [],
    }


def empty_study_teacher_summary() -> StudyTeacherSummary:
    """Build a shape-correct, empty teacher summary."""
    return {
        "summary": "",
        "flags": [],
        "action_items": [],
    }


# ---------------------------------------------------------------------------
# Internal coercion helpers
# ---------------------------------------------------------------------------


def _coerce_str(value: Any) -> str:
    """Force ``value`` to a stripped string; non-strings become ``""``."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _coerce_str_list(value: Any) -> List[str]:
    """Coerce a JSON value to a list of non-empty strings."""
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for entry in value:
        text = _coerce_str(entry)
        if text:
            out.append(text)
    return out


# Matches a leading ``` or ```json fence and the matching trailing ```.
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


def _strip_markdown_fences(raw: str) -> str:
    """
    Remove a single surrounding ```json ... ``` (or plain ```) fence.

    LLMs frequently wrap JSON in markdown fences even when asked not to; we
    accept both ``` and ```json fences and leave the body otherwise untouched.
    """
    if not isinstance(raw, str):
        return ""
    match = _FENCE_RE.match(raw)
    if match:
        return match.group(1).strip()
    return raw.strip()


def _try_load_json(raw: str) -> Optional[dict]:
    """Parse ``raw`` (after fence-stripping) as a JSON object, or return None."""
    text = _strip_markdown_fences(raw)
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


# ---------------------------------------------------------------------------
# Public parsers
# ---------------------------------------------------------------------------


def parse_study_student_response(
    raw: str, *, question: str, rubric_items: Optional[Iterable[str]] = None
) -> StudyStudentFeedback:
    """
    Parse a raw LLM string into a :data:`StudyStudentFeedback`.

    Always returns a well-shaped object with three string arrays. Missing or
    malformed fields fall back to empty arrays.

    ``rubric_items`` is accepted (and ignored) so the previous call sites keep
    working unchanged.
    """
    del rubric_items  # no longer used; accepted for signature compatibility
    parsed = _try_load_json(raw)
    if parsed is None:
        return empty_study_student_feedback(question)

    return {
        "question": _coerce_str(parsed.get("question")) or str(question or ""),
        "high_level_takeaways": _coerce_str_list(parsed.get("high_level_takeaways")),
        "areas_to_improve": _coerce_str_list(parsed.get("areas_to_improve")),
        "next_steps": _coerce_str_list(parsed.get("next_steps")),
    }


def parse_study_teacher_response(raw: str) -> StudyTeacherSummary:
    """
    Parse a raw LLM string into a :data:`StudyTeacherSummary`.

    Falls back to :func:`empty_study_teacher_summary` on any parse error or
    shape mismatch.
    """
    parsed = _try_load_json(raw)
    if parsed is None:
        return empty_study_teacher_summary()

    return {
        "summary": _coerce_str(parsed.get("summary")),
        "flags": _coerce_str_list(parsed.get("flags")),
        "action_items": _coerce_str_list(parsed.get("action_items")),
    }
