"""
OpenAI client for V2 oral examiner.

Responsibilities:
  - generate_question()     — ask OpenAI to produce the next question from the rubric
  - analyze_response()      — check rubric coverage
  - generate_follow_up()    — produce a targeted follow-up for missing rubric items
  - generate_grading_notes() — end-of-session structured grading summary
"""
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings

logger = logging.getLogger(__name__)


def _client():
    from openai import OpenAI
    kwargs = {"api_key": settings.OPENAI_API_KEY}
    if settings.OPENAI_BASE_URL:
        kwargs["base_url"] = settings.OPENAI_BASE_URL
    return OpenAI(**kwargs)


def _chat(
    messages: list,
    max_tokens: int = None,
    temperature: float = None,
    model: str = None,
) -> str:
    t0 = time.time()
    model_name = model or settings.OPENAI_MODEL
    resp = _client().chat.completions.create(
        model=model_name,
        messages=messages,
        max_tokens=max_tokens or settings.OPENAI_MAX_TOKENS,
        temperature=temperature if temperature is not None else settings.OPENAI_TEMPERATURE,
        reasoning_effort=settings.OPENAI_REASONING_EFFORT,
    )
    elapsed = time.time() - t0
    text = resp.choices[0].message.content.strip()
    logger.info("OpenAI call: %.2fs, %d chars returned", elapsed, len(text))
    return text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_question(system_prompt: str, question_text: str, rubric_items: list) -> str:
    """
    Return the question exactly as the proctor should speak it.
    We trust the teacher-written question_text but let OpenAI lightly rephrase
    into a natural spoken form if needed.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": (
            f"Please ask the student the following question in a natural, spoken way. "
            f"Do not add hints. Output only the question text, nothing else.\n\n"
            f"Question: {question_text}\n\n"
            f"Rubric items being assessed:\n" +
            "\n".join(f"- {r}" for r in rubric_items)
        )},
    ]
    return _chat(messages, max_tokens=200)


def analyze_response(
    system_prompt: str,
    question: str,
    rubric_items: list,
    student_transcript: str,
    lecture_material: str = "",
) -> dict:
    """
    Returns:
        {
            "items": [
                {"item": str, "status": "Met"|"Partial"|"Missing", "evidence": str},
                ...
            ]
        }
    """
    rubric_block = "\n".join(f"- {r}" for r in rubric_items)
    lecture_block = (
        f"\n\nLecture/source material the student was taught (use to judge correctness):\n{lecture_material}\n"
        if lecture_material.strip() else ""
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": (
            f"Question asked: {question}\n\n"
            f"Rubric items:\n{rubric_block}\n\n"
            f"Student's answer:\n{student_transcript}"
            f"{lecture_block}\n\n"
            "For each rubric item, respond with JSON in this exact format:\n"
            '{"items": [{"item": "<rubric item>", "status": "Met"|"Partial"|"Missing", "evidence": "<brief quote or \'not mentioned\'>"}, ...]}'
        )},
    ]
    raw = _chat(messages, max_tokens=500)
    try:
        # Strip markdown code fences if present
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        return json.loads(clean.strip())
    except Exception:
        logger.warning("Could not parse analysis JSON; returning raw: %s", raw[:200])
        return {"items": []}


def generate_follow_up(
    system_prompt: str,
    question: str,
    rubric_items: list,
    missing_items: list,
    mini_transcript_text: str,
    lecture_material: str = "",
    already_asked_follow_ups: list = None,
) -> str:
    """
    Generate one targeted follow-up question for the missing rubric items.
    If lecture_material is provided, draw from it to form the follow-up.
    mini_transcript_text: plain text of the mini-transcript (text events only, no paths).
    already_asked_follow_ups: list of follow-up question texts already asked—do not repeat or rephrase these.
    Returns question string.
    """
    already_asked_follow_ups = already_asked_follow_ups or []
    missing_block = "\n".join(f"- {m}" for m in missing_items)
    lecture_block = (
        f"\n\nLecture/source material to draw from when asking the follow-up:\n{lecture_material}\n"
        if lecture_material.strip() else ""
    )
    no_repeat_block = ""
    if already_asked_follow_ups:
        no_repeat_block = (
            "\n\nFollow-up questions you have ALREADY asked (you MUST NOT repeat or rephrase these; ask something completely different):\n"
            + "\n".join(f"- {q}" for q in already_asked_follow_ups)
            + "\n\n"
        )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": (
            f"Original question: {question}\n\n"
            f"What the student said so far (transcript):\n{mini_transcript_text}\n\n"
            f"Missing rubric items the student has NOT addressed:\n{missing_block}"
            f"{lecture_block}"
            f"{no_repeat_block}"
            "Generate ONE focused follow-up question. "
            "Do NOT repeat or rephrase any follow-up you have already asked; ask about a different missing aspect or in a different way. "
            "If the student gave a very short or vague answer, you may ask them to elaborate, explain further, or give an example. "
            "Otherwise probe the missing rubric items; if lecture material is provided, base the follow-up on that content. "
            "Be natural and conversational. Output only the question, nothing else."
        )},
    ]
    return _chat(
        messages,
        max_tokens=150,
    )


def generate_grading_notes(
    system_prompt: str,
    exam_config: dict,
    final_transcript_md: str,
) -> str:
    """
    End-of-session grading notes based on the full final transcript.
    If exam_config contains lecture_material, use it to inform the grading.
    Returns a markdown string.
    """
    lecture = (exam_config.get("lecture_material") or "").strip()
    lecture_block = (
        f"\n\nLecture/source material for this exam (use to assess correctness and gaps):\n{lecture}\n"
        if lecture else ""
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": (
            "The oral exam is complete. Below is the full timestamped transcript.\n\n"
            f"{final_transcript_md}"
            f"{lecture_block}\n\n"
            "Please write structured grading notes covering:\n"
            "1. Which rubric items were fully met, partially met, or missed for each question\n"
            "2. Strengths shown by the student\n"
            "3. Gaps or misconceptions\n"
            "4. Suggested follow-up study areas\n"
            "Be concise and evidence-based, citing specific moments from the transcript."
        )},
    ]
    return _chat(messages, max_tokens=1000, temperature=0.3)
