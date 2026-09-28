"""
Build the student-facing post-session feedback for one study run.

The post-session report is a **summarization** of the per-capture feedback
produced during the session (see ``vision_feedback.request_paper_feedback``).
The summarizer consumes every capture's grader JSON + markdown and emits a
single document organized into three standardized bulleted sections:

- ``high_level_takeaways`` - what the student should walk away knowing.
- ``areas_to_improve``     - specific gaps the captures revealed.
- ``next_steps``           - concrete, actionable advice for what to do next.

Top-down responsibility split:

1. :func:`_build_student_prompt` - pure string builder; trivially testable.
2. :func:`_invoke_llm`           - call the injected ``llm_complete_fn``.
3. :func:`parse_study_student_response` (in ``feedback_contracts``) - normalize
   the raw LLM output into a :data:`StudyStudentFeedback`.
4. :func:`build_study_student_feedback` - public orchestrator that wires the
   above and falls back to :func:`empty_study_student_feedback` on any error.
"""

from __future__ import annotations

import json
from typing import Callable, Iterable, List

from .feedback_aggregation import CaptureRecord
from .feedback_contracts import (
    StudyStudentFeedback,
    empty_study_student_feedback,
    parse_study_student_response,
)


# ``llm_complete_fn`` is any callable matching ``(system, user) -> str``.
LLMComplete = Callable[[str, str], str]


_SYSTEM_PROMPT = (
    "You are Socrates, a kind, concise teaching assistant writing a short "
    "post-session report that will be shown DIRECTLY to the learner who "
    "just finished a study run on one practice problem. You are given the "
    "question, its rubric, and the per-capture feedback the in-session "
    "vision grader already produced for each photo of their paper. Your "
    "job is to SUMMARIZE that in-session feedback across all captures into "
    "exactly three sections: High-level takeaways, Areas to improve, and "
    "Next Steps (concrete actionable advice). "
    "Tone: warm, respectful, and encouraging — like a supportive coach. "
    "Celebrate what they did well before or alongside any critique. "
    "In \"areas_to_improve\", use constructive, forward-looking language "
    "(what to try next), not shame, sarcasm, or a pile-on of faults. "
    "Avoid harsh words such as \"wrong\", \"failed\", \"bad\", or \"obvious\". "
    "Voice: write in second person, addressed to the learner. Use \"you\" "
    "and \"your\". Do NOT say \"the student\" and do NOT refer to the "
    "learner in the third person anywhere in your output. "
    "Do not invent observations that are not grounded in the per-capture "
    "feedback above. "
    "Return ONE JSON object only - no prose, no markdown fences."
)


# ---------------------------------------------------------------------------
# Prompt construction (pure)
# ---------------------------------------------------------------------------


def _format_capture(record: CaptureRecord) -> str:
    """Render one capture as a short, LLM-friendly text block."""
    grade_blob = json.dumps(record.feedback_json, indent=2) if record.feedback_json else "{}"
    md = record.feedback_md.strip() or "(no markdown feedback recorded)"
    return (
        f"--- Capture {record.index} ({record.image_filename}) ---\n"
        f"Per-capture grader JSON:\n{grade_blob}\n\n"
        f"Per-capture grader markdown:\n{md}"
    )


def _build_student_prompt(
    *,
    question_text: str,
    rubric_items: Iterable[str],
    captures: Iterable[CaptureRecord],
) -> tuple[str, str]:
    """
    Construct ``(system, user)`` strings.

    The user prompt is grounded in the question, every rubric item, and every
    capture so tests can assert "the prompt actually mentions everything we
    handed in" - this grounding is what makes the summary "based on the
    in-session feedback" rather than a hallucinated roll-up.
    """
    rubric_list: List[str] = [str(r) for r in (rubric_items or [])]
    capture_list: List[CaptureRecord] = list(captures or [])

    rubric_block = "\n".join(f"- {r}" for r in rubric_list) or "(no rubric items)"

    if capture_list:
        captures_block = "\n\n".join(_format_capture(c) for c in capture_list)
    else:
        captures_block = "(no captures were taken during this study run)"

    schema_block = (
        '{\n'
        '  "question": "<echo of the question text>",\n'
        '  "high_level_takeaways": ["<bullet>", "..."],\n'
        '  "areas_to_improve": ["<bullet>", "..."],\n'
        '  "next_steps": ["<bullet>", "..."]\n'
        '}'
    )

    user = (
        f"Question:\n{question_text.strip() or '(empty)'}\n\n"
        f"Rubric items (use these as the scoring frame for what good looks like):\n"
        f"{rubric_block}\n\n"
        f"Student work captures (this is the in-session feedback you are summarizing):\n"
        f"{captures_block}\n\n"
        "Write the post-session report as a JSON object with this exact schema:\n"
        f"{schema_block}\n\n"
        "Rules:\n"
        "- Produce 3-6 short bullets per section. Each bullet is one sentence.\n"
        "- Ground every bullet in the per-capture grader output above; reference "
        "specific captures when it helps (e.g. \"see capture 2\").\n"
        "- \"high_level_takeaways\" summarizes what you did and understood "
        "across all captures; lead with strengths and real progress where the captures support it.\n"
        "- \"areas_to_improve\" names specific gaps the captures revealed, phrased kindly "
        "(one idea per bullet; coaching tone, not a lecture).\n"
        "- \"next_steps\" gives concrete, doable advice you can try next — small wins, not an overwhelming list.\n"
        "- Write every bullet addressed to the learner in second person (\"you\"/\"your\"). "
        "Never say \"the student\" or refer to them in the third person.\n"
        "- If a section has nothing to say, emit an empty array for it rather than "
        "padding with filler.\n"
        "- Return JSON only - no markdown fences, no commentary."
    )
    return _SYSTEM_PROMPT, user


# ---------------------------------------------------------------------------
# LLM invocation (thin wrapper; isolates the side effect)
# ---------------------------------------------------------------------------


def _invoke_llm(llm_complete_fn: LLMComplete, system: str, user: str) -> str:
    """Call ``llm_complete_fn`` and coerce the result to a string."""
    raw = llm_complete_fn(system, user)
    return raw if isinstance(raw, str) else str(raw or "")


# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------


def build_study_student_feedback(
    *,
    question_text: str,
    rubric_items: Iterable[str],
    captures: Iterable[CaptureRecord],
    llm_complete_fn: LLMComplete,
) -> StudyStudentFeedback:
    """
    Generate the three-section post-session summary for one study run.

    Any exception from the LLM call - or any parser-level shape error - is
    swallowed and converted to :func:`empty_study_student_feedback` so the
    caller can always rely on a well-formed object and a flaky model never
    breaks the rest of the ``/end`` pipeline.
    """
    rubric_list = [str(r) for r in (rubric_items or [])]
    try:
        system, user = _build_student_prompt(
            question_text=question_text,
            rubric_items=rubric_list,
            captures=captures,
        )
        raw = _invoke_llm(llm_complete_fn, system, user)
    except Exception:
        return empty_study_student_feedback(question_text)

    return parse_study_student_response(raw, question=question_text)


# ---------------------------------------------------------------------------
# Multi-question variant
#
# Multi-question study runs (question-bank selection mode) need a single
# aggregate three-bucket summary, *not* a per-question object. These helpers
# do exactly one LLM call that sees every question, every rubric, and every
# capture grouped by question, and emit the same v1 ``StudyStudentFeedback``
# shape the single-question builder returns.
# ---------------------------------------------------------------------------


# ``(question_text, rubric_items)`` pair for one practice problem.
QuestionSpec = tuple[str, List[str]]


_SYSTEM_PROMPT_MULTI = (
    "You are Socrates, a kind, concise teaching assistant writing a short "
    "post-session report that will be shown DIRECTLY to the learner who "
    "just finished a study run across one or more practice problems. You "
    "are given each question, its rubric, and the per-capture feedback "
    "the in-session vision grader already produced for each photo of "
    "their paper, grouped by question. Your job is to SUMMARIZE that "
    "in-session feedback across ALL questions and ALL captures into "
    "exactly three sections: High-level takeaways, Areas to improve, and "
    "Next Steps (concrete actionable advice). "
    "Tone: warm, respectful, and encouraging — like a supportive coach. "
    "Celebrate real progress where the captures support it; phrase gaps as "
    "the next step to try, not as blame. Avoid harsh words such as \"wrong\", "
    "\"failed\", \"bad\", or \"obvious\". "
    "Voice: write in second person, addressed to the learner. Use \"you\" "
    "and \"your\". Do NOT say \"the student\" and do NOT refer to the "
    "learner in the third person anywhere in your output. "
    "Do not invent observations that are not grounded in the per-capture "
    "feedback above. Return ONE JSON object only - no prose, no markdown fences."
)


def _normalize_specs(questions: Iterable[QuestionSpec]) -> List[QuestionSpec]:
    """Coerce an iterable of ``(text, rubric_items)`` pairs to plain strings."""
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


def _build_student_prompt_multi(
    *,
    questions: Iterable[QuestionSpec],
    captures: Iterable[CaptureRecord],
) -> tuple[str, str]:
    """
    Construct ``(system, user)`` strings for a multi-question aggregate run.

    The user prompt groups inputs by question in declared order so tests can
    assert that (a) every question/rubric/capture is present, and (b) the
    capture group for Question k sits under the ``=== Captures for Question k ===``
    header regardless of the order the captures were recorded in.
    """
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

    schema_block = (
        '{\n'
        '  "question": "<short label naming the run, e.g. \'Study session across N questions\'>",\n'
        '  "high_level_takeaways": ["<bullet>", "..."],\n'
        '  "areas_to_improve": ["<bullet>", "..."],\n'
        '  "next_steps": ["<bullet>", "..."]\n'
        '}'
    )

    user = (
        f"Questions in this study run:\n{questions_section}\n\n"
        f"Student work captures (grouped by question; this is the in-session feedback you are summarizing):\n"
        f"{captures_section}\n\n"
        "Write the post-session report as a JSON object with this exact schema:\n"
        f"{schema_block}\n\n"
        "Rules:\n"
        "- Produce 3-6 short bullets per section across all questions. Each bullet is one sentence.\n"
        "- Ground every bullet in the per-capture grader output above; reference "
        "specific captures or questions when it helps (e.g. \"Q1 capture 2\").\n"
        "- \"high_level_takeaways\" summarizes what you did and understood across all questions; include strengths first where supported.\n"
        "- \"areas_to_improve\" names specific gaps across all questions in a kind, coaching tone (one main idea per bullet when possible).\n"
        "- \"next_steps\" gives concrete, doable advice — small wins, not an overwhelming list.\n"
        "- Write every bullet addressed to the learner in second person (\"you\"/\"your\"). "
        "Never say \"the student\" or refer to them in the third person.\n"
        "- If a section has nothing to say, emit an empty array for it rather than padding with filler.\n"
        "- Return JSON only - no markdown fences, no commentary."
    )
    return _SYSTEM_PROMPT_MULTI, user


def build_study_student_feedback_multi(
    *,
    questions: Iterable[QuestionSpec],
    captures: Iterable[CaptureRecord],
    llm_complete_fn: LLMComplete,
) -> StudyStudentFeedback:
    """
    Generate ONE three-bucket post-session summary covering every question.

    Exactly one LLM call is made. Any exception or parser shape error falls
    back to :func:`empty_study_student_feedback` so the ``/end`` pipeline
    always has a well-formed object to persist.
    """
    try:
        system, user = _build_student_prompt_multi(
            questions=questions, captures=captures
        )
        raw = _invoke_llm(llm_complete_fn, system, user)
    except Exception:
        return empty_study_student_feedback("")

    return parse_study_student_response(raw, question="")
