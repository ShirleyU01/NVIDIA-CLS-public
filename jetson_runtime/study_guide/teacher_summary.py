"""
Build the teacher-facing post-session summary for one study run.

Mirrors the structure of :mod:`student_summary` but produces a much shorter,
narrative roll-up instead of per-rubric rows. The teacher prompt is grounded
in *both* the per-capture grader output and the student-facing feedback we
just generated, so the instructor sees consistent language across surfaces.
"""

from __future__ import annotations

import json
from typing import Callable, Iterable, List

from .feedback_aggregation import CaptureRecord
from .feedback_contracts import (
    StudyStudentFeedback,
    StudyTeacherSummary,
    empty_study_teacher_summary,
    parse_study_teacher_response,
)


# ``llm_complete_fn`` is any callable matching ``(system, user) -> str``.
LLMComplete = Callable[[str, str], str]


_SYSTEM_PROMPT = (
    "You are an instructor's TA writing a short, candid roll-up about a "
    "single student's study run on one practice problem. The instructor will "
    "use this to decide what to address with the student in the next session. "
    "Be concise and concrete; do not pad. Return ONE JSON object only - "
    "no prose, no markdown fences."
)


# ---------------------------------------------------------------------------
# Prompt construction (pure)
# ---------------------------------------------------------------------------


def _format_capture(record: CaptureRecord) -> str:
    """Render one capture's grader artifacts into the teacher prompt."""
    grade_blob = json.dumps(record.feedback_json, indent=2) if record.feedback_json else "{}"
    return (
        f"--- Capture {record.index} ({record.image_filename}) ---\n"
        f"{grade_blob}"
    )


def _format_student_feedback(student_feedback: StudyStudentFeedback) -> str:
    """Render the just-built student feedback as plain JSON for grounding."""
    return json.dumps(student_feedback, indent=2)


def _build_teacher_prompt(
    *,
    question_text: str,
    rubric_items: Iterable[str],
    captures: Iterable[CaptureRecord],
    student_feedback: StudyStudentFeedback,
) -> tuple[str, str]:
    """Construct ``(system, user)`` strings, fully grounded in upstream data."""
    rubric_list: List[str] = [str(r) for r in (rubric_items or [])]
    capture_list: List[CaptureRecord] = list(captures or [])

    rubric_block = "\n".join(f"- {r}" for r in rubric_list) or "(no rubric items)"
    if capture_list:
        captures_block = "\n\n".join(_format_capture(c) for c in capture_list)
    else:
        captures_block = "(no captures were taken during this study run)"
    student_block = _format_student_feedback(student_feedback)

    schema_block = (
        '{\n'
        '  "summary": "2-3 sentence narrative for the instructor",\n'
        '  "flags":   ["short risk/struggle bullets"],\n'
        '  "action_items": ["concrete next step the instructor can take"]\n'
        '}'
    )

    user = (
        f"Question:\n{question_text.strip() or '(empty)'}\n\n"
        f"Rubric items:\n{rubric_block}\n\n"
        f"Per-capture grader output:\n{captures_block}\n\n"
        f"Student-facing feedback we just generated:\n{student_block}\n\n"
        "Write the instructor roll-up as a JSON object with this exact schema:\n"
        f"{schema_block}\n\n"
        "Rules:\n"
        "- summary: 2-3 sentences. Be candid about what the student did and didn't do.\n"
        "- flags: short bullets (3-7 words each). Empty list if nothing notable.\n"
        "- action_items: concrete next moves the instructor can take. Empty list is OK.\n"
        "- Return JSON only - no markdown fences, no commentary."
    )
    return _SYSTEM_PROMPT, user


# ---------------------------------------------------------------------------
# LLM invocation
# ---------------------------------------------------------------------------


def _invoke_llm(llm_complete_fn: LLMComplete, system: str, user: str) -> str:
    """Call ``llm_complete_fn`` and coerce the result to a string."""
    raw = llm_complete_fn(system, user)
    return raw if isinstance(raw, str) else str(raw or "")


# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------


def build_study_teacher_summary(
    *,
    question_text: str,
    rubric_items: Iterable[str],
    captures: Iterable[CaptureRecord],
    student_feedback: StudyStudentFeedback,
    llm_complete_fn: LLMComplete,
) -> StudyTeacherSummary:
    """
    Generate the instructor roll-up for one study run.

    Falls back to :func:`empty_study_teacher_summary` on any LLM or parser
    error so the ``/end`` pipeline always has a well-shaped object to persist.
    """
    try:
        system, user = _build_teacher_prompt(
            question_text=question_text,
            rubric_items=rubric_items,
            captures=captures,
            student_feedback=student_feedback,
        )
        raw = _invoke_llm(llm_complete_fn, system, user)
    except Exception:
        return empty_study_teacher_summary()

    return parse_study_teacher_response(raw)


# ---------------------------------------------------------------------------
# Multi-question variant
#
# Analogous to ``build_study_student_feedback_multi``: a single aggregate
# LLM call produces one ``{summary, flags, action_items}`` roll-up covering
# every question in the run.
# ---------------------------------------------------------------------------


# ``(question_text, rubric_items)`` pair for one practice problem.
QuestionSpec = tuple[str, List[str]]


_SYSTEM_PROMPT_MULTI = (
    "You are an instructor's TA writing a short, candid roll-up about a "
    "single student's study run across one or more practice problems. The "
    "instructor will use this to decide what to address with the student in "
    "the next session. Be concise and concrete; do not pad. Return ONE JSON "
    "object only - no prose, no markdown fences."
)


def _normalize_specs(questions: Iterable[QuestionSpec]) -> List[QuestionSpec]:
    out: List[QuestionSpec] = []
    for q in questions or []:
        text = str(q[0]) if q and len(q) > 0 else ""
        rubric = [str(r) for r in (q[1] if q and len(q) > 1 and q[1] else [])]
        out.append((text, rubric))
    return out


def _render_question_block(index_1: int, text: str, rubric: List[str]) -> str:
    rubric_block = "\n".join(f"- {r}" for r in rubric) or "(no rubric items)"
    return (
        f"=== Question {index_1} ===\n"
        f"{text.strip() or '(empty)'}\n\n"
        f"Rubric:\n{rubric_block}"
    )


def _render_captures_for_question(
    index_1: int, group: List[CaptureRecord]
) -> str:
    if group:
        body = "\n\n".join(_format_capture(c) for c in group)
    else:
        body = "(no captures for this question)"
    return f"=== Captures for Question {index_1} ===\n{body}"


def _build_teacher_prompt_multi(
    *,
    questions: Iterable[QuestionSpec],
    captures: Iterable[CaptureRecord],
    student_feedback: StudyStudentFeedback,
) -> tuple[str, str]:
    """Construct ``(system, user)`` strings for a multi-question aggregate run."""
    qlist = _normalize_specs(questions)
    capture_list: List[CaptureRecord] = list(captures or [])

    if qlist:
        questions_section = "\n\n".join(
            _render_question_block(i + 1, text, rubric)
            for i, (text, rubric) in enumerate(qlist)
        )
    else:
        questions_section = "(no questions)"

    if capture_list:
        blocks: List[str] = []
        for i in range(len(qlist)):
            group = [c for c in capture_list if c.question_index == i]
            blocks.append(_render_captures_for_question(i + 1, group))

        max_idx = len(qlist)
        unlinked = [
            c for c in capture_list
            if c.question_index < 0 or c.question_index >= max_idx
        ]
        if unlinked:
            blocks.append(
                "=== Unlinked captures ===\n"
                + "\n\n".join(_format_capture(c) for c in unlinked)
            )
        captures_section = "\n\n".join(blocks)
    else:
        captures_section = "(no captures were taken during this study run)"

    student_block = _format_student_feedback(student_feedback)

    schema_block = (
        '{\n'
        '  "summary": "2-3 sentence narrative for the instructor",\n'
        '  "flags":   ["short risk/struggle bullets"],\n'
        '  "action_items": ["concrete next step the instructor can take"]\n'
        '}'
    )

    user = (
        f"Questions in this study run:\n{questions_section}\n\n"
        f"Per-capture grader output (grouped by question):\n{captures_section}\n\n"
        f"Student-facing feedback we just generated:\n{student_block}\n\n"
        "Write the instructor roll-up as a JSON object with this exact schema:\n"
        f"{schema_block}\n\n"
        "Rules:\n"
        "- summary: 2-3 sentences. Be candid about what the student did and didn't do across all questions.\n"
        "- flags: short bullets (3-7 words each). Empty list if nothing notable.\n"
        "- action_items: concrete next moves the instructor can take. Empty list is OK.\n"
        "- Return JSON only - no markdown fences, no commentary."
    )
    return _SYSTEM_PROMPT_MULTI, user


def build_study_teacher_summary_multi(
    *,
    questions: Iterable[QuestionSpec],
    captures: Iterable[CaptureRecord],
    student_feedback: StudyStudentFeedback,
    llm_complete_fn: LLMComplete,
) -> StudyTeacherSummary:
    """Generate ONE instructor roll-up across every question in the run."""
    try:
        system, user = _build_teacher_prompt_multi(
            questions=questions,
            captures=captures,
            student_feedback=student_feedback,
        )
        raw = _invoke_llm(llm_complete_fn, system, user)
    except Exception:
        return empty_study_teacher_summary()

    return parse_study_teacher_response(raw)
