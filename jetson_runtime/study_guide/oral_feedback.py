"""LLM grading for spoken (transcribed) study answers — no paper images."""

from __future__ import annotations

from typing import Any, Optional

from config import settings
from study_guide.vision_feedback import (
    PaperFeedback,
    _STUDENT_FEEDBACK_HEADING_RE,
    _extract_json_and_markdown,
    _extract_student_feedback_section,
    _strip_leading_json_runs,
    sanitize_student_feedback_markdown,
)


def request_oral_feedback(
    *,
    question_text: str,
    rubric_items: list[str],
    transcript: str,
    model: Optional[str] = None,
) -> PaperFeedback:
    """Grade a student's spoken answer from STT transcript text."""
    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
    model_name = model or getattr(settings, "STUDY_GUIDE_MODEL", None) or settings.OPENAI_MODEL

    rubric_block = "\n".join(f"- {r}" for r in rubric_items)
    spoken = (transcript or "").strip() or "(No speech detected.)"
    prompt = (
        "You are a supportive teaching assistant helping a student practice exam problems.\n"
        "The student answered **by speaking**; below is a speech-to-text transcript of what they said "
        "(it may contain disfluencies, filler words, or minor transcription errors — infer their intent).\n\n"
        f"Problem:\n{question_text}\n\n"
        f"Rubric items:\n{rubric_block}\n\n"
        f"Student's spoken answer (transcript):\n{spoken}\n\n"
        "Task:\n"
        "- Infer their approach from what they said.\n"
        "- Give immediate, concrete feedback aligned with the rubric.\n"
        "- When the work has multiple steps, be step-by-step.\n"
        "- Ask 1-2 clarifying questions only if the transcript is too vague to assess.\n\n"
        "Tone: warm, supportive coach — same warmth requirements as paper-based study feedback.\n"
        "Mathematics in the student-facing markdown: KaTeX with only `$...$` or `$$...$$`.\n\n"
        "Output TWO things in this strict order:\n"
        "1) A single JSON object (machine-readable). Keys: summary, rubric (array of "
        "{item, status: Met|Partial|Missing, evidence}), correctness "
        "(Correct|Partially correct|Incorrect|Unclear), key_mistakes, next_steps, clarifying_questions.\n"
        "2) A blank line, then markdown beginning with exactly: ## Student feedback\n"
        "   (polished prose for the student; no JSON or code fences in this section).\n"
        "   Mention **Ask me anything** when a conversational follow-up would help, using that exact wording.\n"
    )

    resp = client.responses.create(
        model=model_name,
        input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
    )
    text = ""
    try:
        text = resp.output_text or ""
    except Exception:
        text = str(resp)

    parsed, md = _extract_json_and_markdown(text)
    if not md.strip():
        if _STUDENT_FEEDBACK_HEADING_RE.search(text):
            md = _extract_student_feedback_section(text)
        else:
            md = _strip_leading_json_runs((text or "").strip())
    if not parsed:
        parsed = {"summary": "Unparsed response", "raw": (text or "").strip()}

    md = sanitize_student_feedback_markdown(md)
    return PaperFeedback(md=md.strip(), json=parsed)
