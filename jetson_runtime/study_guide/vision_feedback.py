from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from config import settings


_JSON_FENCE_RE = re.compile(r"```\s*json\s*\r?\n([\s\S]*?)```", re.IGNORECASE)
_GENERIC_FENCE_RE = re.compile(r"```[^\n]*\r?\n([\s\S]*?)```", re.MULTILINE)
_STUDENT_FEEDBACK_HEADING_RE = re.compile(
    r"^##\s*Student\s+feedback\s*$", re.IGNORECASE | re.MULTILINE
)
_JSON_SCHEMA_MARKERS = (
    '"correctness"',
    '"summary"',
    '"rubric"',
    '"key_mistakes"',
    '"next_steps"',
    '"clarifying_questions"',
)


def _split_leading_json_object(cleaned: str) -> tuple[Optional[dict[str, Any]], str]:
    """
    If ``cleaned`` begins with a single JSON object, parse it and return (obj, remainder).
    Otherwise return (None, cleaned). Bracket matching does not respect string literals.
    """
    if not cleaned.startswith("{"):
        return None, cleaned
    depth = 0
    end_idx: int | None = None
    for i, ch in enumerate(cleaned):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_idx = i + 1
                break
    if end_idx is None:
        return None, cleaned
    blob = cleaned[:end_idx]
    rest = cleaned[end_idx:].strip()
    try:
        return json.loads(blob), rest
    except Exception:
        return None, cleaned


def _is_json_like_blob(blob: str) -> bool:
    st = (blob or "").strip()
    if not st:
        return False
    if st[0] in "{[":
        try:
            json.loads(st)
            return True
        except Exception:
            pass
    lowered = st.lower()
    return any(marker in lowered for marker in _JSON_SCHEMA_MARKERS) and "{" in st


def _extract_student_feedback_section(text: str) -> str:
    """Keep only the canonical student-facing section when the model included it."""
    match = _STUDENT_FEEDBACK_HEADING_RE.search(text)
    if not match:
        return text
    return text[match.start() :].strip()


def _strip_json_fences(text: str) -> str:
    prev = None
    while prev != text:
        prev = text
        text = _JSON_FENCE_RE.sub("", text).strip()

        def _fence_replacer(match: re.Match[str]) -> str:
            inner = match.group(1).strip()
            return "" if _is_json_like_blob(inner) else match.group(0)

        text = _GENERIC_FENCE_RE.sub(_fence_replacer, text).strip()
    return text


def _strip_leading_json_object(s: str, *, min_rest_len: int = 1) -> str:
    st = s.lstrip()
    parsed, rest = _split_leading_json_object(st)
    if parsed is None or len(rest.strip()) < min_rest_len:
        return s
    return rest.strip()


def _strip_leading_json_runs(text: str) -> str:
    while True:
        stripped = _strip_leading_json_object(text)
        if stripped == text:
            break
        text = stripped
    return text


def _strip_json_after_heading(text: str) -> str:
    """
    Remove a JSON blob that appears immediately after ``## Student feedback``
    before the real prose (a common model leak).
    """
    match = _STUDENT_FEEDBACK_HEADING_RE.search(text)
    if not match:
        return text
    heading = match.group(0)
    body = text[match.end() :].lstrip("\n")
    body = _strip_json_fences(body)
    body = _strip_leading_json_runs(body)
    if not body:
        return heading
    return f"{heading}\n\n{body}".strip()


def sanitize_student_feedback_markdown(md: str) -> str:
    """
    Strip JSON/code-fence leakage and fix LaTeX so KaTeX can render it.

    Steps:
    1. Keep only the ``## Student feedback`` section when present.
    2. Remove any JSON objects / fenced JSON blocks that leaked in.
    3. Normalize LaTeX delimiters and fix double-backslash commands.
    """
    from study_guide.latex_fix import fix_latex_for_katex  # local to jetson_runtime

    text = (md or "").strip()
    if not text:
        return text

    text = _extract_student_feedback_section(text)
    text = _strip_json_fences(text)
    text = _strip_leading_json_runs(text)
    text = _strip_json_after_heading(text)
    text = _strip_json_fences(text)
    text = _strip_leading_json_runs(text)
    text = fix_latex_for_katex(text)
    return text.strip()


def _image_to_data_url(image_path: Path) -> str:
    data = image_path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    # JPEG is what we capture; keep it simple.
    return f"data:image/jpeg;base64,{b64}"


@dataclass
class PaperFeedback:
    md: str
    json: dict[str, Any]


def _extract_json_and_markdown(text: str) -> tuple[dict[str, Any], str]:
    """
    Best-effort extraction for responses that look like:
      <optional prose>
      ```json
      {...}
      ```
      <markdown feedback>

    or:
      {...}<newline><markdown>
    """
    raw = (text or "").strip()
    if not raw:
        return {}, ""

    cleaned = raw

    # Prefer a leading raw JSON object so ```json fences *inside* the markdown
    # section cannot hijack extraction.
    parsed_lead, rest_lead = _split_leading_json_object(cleaned)
    if parsed_lead is not None:
        return parsed_lead, rest_lead

    if "```" in cleaned:
        lower = cleaned.lower()
        fence_idx = lower.find("```json")
        if fence_idx != -1:
            after = cleaned[fence_idx + len("```json") :]
            end = after.find("```")
            if end != -1:
                json_block = after[:end].strip()
                rest = after[end + 3 :].strip()
                try:
                    return json.loads(json_block), rest
                except Exception:
                    pass

    # Find first JSON object anywhere in the string.
    first = cleaned.find("{")
    if first == -1:
        return {}, cleaned

    depth = 0
    end_idx = None
    for i, ch in enumerate(cleaned[first:], start=first):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_idx = i + 1
                break

    if end_idx is None:
        return {}, cleaned

    json_part = cleaned[first:end_idx]
    rest = (cleaned[end_idx:]).strip()
    try:
        parsed = json.loads(json_part)
        return parsed, rest
    except Exception:
        return {}, cleaned


def request_paper_feedback(
    *,
    question_text: str,
    rubric_items: list[str],
    image_paths: list[Path],
    model: Optional[str] = None,
) -> PaperFeedback:
    """
    Send (question + rubric + paper images) to the LLM and request structured feedback.
    Uses the OpenAI Responses API (OpenAI Python SDK v2+).
    """
    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)

    model_name = model or getattr(settings, "STUDY_GUIDE_MODEL", None) or settings.OPENAI_MODEL

    rubric_block = "\n".join(f"- {r}" for r in rubric_items)
    prompt = (
        "You are a supportive teaching assistant helping a student practice exam problems.\n"
        "The student works on paper; you are given photos that may include their solution **and** notes or questions written to you.\n\n"
        f"Problem:\n{question_text}\n\n"
        f"Rubric items:\n{rubric_block}\n\n"
        "Questions written on the paper (to you or about the task):\n"
        "- If you see a **clear question** on the page (margin note, \"?\", \"why\", \"is this right\", \"how do I...\", etc.), you **must** still answer it **and** give full feedback on the assigned problem — but keep it **one natural read**, not two stacked templates.\n"
        "- **Do not** use stiff headings or labels such as \"The answer to your question\", \"Your question\", \"Response\", \"Regarding your question\", or `### Your question` / `### Answer`. Those read like a form, not a tutor.\n"
        "- **Do** start `## Student feedback` with the required acknowledgement opener (**Excellent —** / **Great job —** / …) as the **very first sentence of the whole section**. In that same opening paragraph (or immediately in the next short one), weave in a **brief, direct** reply to what they asked — e.g. quote or paraphrase their note, answer it, then pivot smoothly into how their **solution to the problem** looks (what worked, what to tighten). It should feel like one conversation, not \"answer block\" then \"feedback block\".\n"
        "- Use extra paragraphs or bullets only for clarity; the transition from answering their note to commenting on their work should not feel like a hard reset.\n\n"
        "Task:\n"
        "- First, infer the student's approach from the paper.\n"
        "- Then give immediate, concrete feedback.\n"
        "- When the work has multiple steps, be step-by-step and point to where it goes correct or incorrect.\n"
        "- Ask 1-2 clarifying questions **only** if you truly cannot tell what they meant or the photo does not show enough of the work — not merely because the answer is short.\n\n"
        "Concise and notation-based answers (critical):\n"
        "- Standard math shorthand can be a **complete** answer. Examples: `n!`, `5!`, `\\binom{n}{k}`, `P(n,r)`, `n^k`, a single simplified number, or a short expression that matches what the question asked for.\n"
        "- If such notation correctly answers the question (e.g. \"how many ways to arrange 5 distinct books\" → `5!` or `120`), treat it as **clear** and **correct** in `correctness` and in your prose. Praise it; do **not** say it is \"not clear\" or \"incomplete\" just because they did not write sentences or show every intermediate step.\n"
        "- Reserve `correctness: Unclear` and \"unclear\" wording only when the work is off-topic or the symbols genuinely **cannot** be tied to the question, or when **no** meaningful written work is visible — not for terse but valid mathematics, and not for mild blur/glare/compression if you can still read the answer.\n\n"
        "Tone for the student-facing markdown (section 2 below) — warmth is required:\n"
        "- Sound like a supportive coach, never like a harsh examiner. The learner should feel respected and capable.\n"
        "- Be fair and genuinely encouraging. Partially correct reasoning counts — do not expect a word-for-word match to the mark scheme.\n"
        "- Prefer \"we\" or neutral phrasing for fixes (e.g. \"next step\", \"one thing to tighten\") over blaming \"you\" for mistakes.\n"
        "- Avoid cold or shaming wording in prose and in JSON string fields (`summary`, `evidence`, `key_mistakes`, `next_steps`, `clarifying_questions`): "
        "do not use \"wrong\", \"failed\", \"bad\", \"obvious\", \"simply\", \"just\", or \"should have\". "
        "Use gentle alternatives: \"not quite there yet\", \"almost\", \"let's adjust\", \"worth double-checking\", \"a small slip\". "
        "(You must still use the exact `correctness` enum values where applicable — that label is for the app, not spoken aloud to the student.)\n"
        "- When something is off, name **one** concrete improvement at a time where possible; do not pile on a long list of faults.\n"
        "- The **first sentence** of `## Student feedback` (the whole section, including when they left a note on the paper) must open with a short acknowledgement that matches how much they got right on the **assigned problem**, "
        "then an em dash, then the rest of that sentence — you may fold their margin question into that opener or finish answering it in the very next sentence without a heading. Choose ONE opener by overall merit:\n"
        "  • Mostly correct / strong work → start with: Excellent —\n"
        "  • Solid progress with meaningful gaps → start with: Great job —\n"
        "  • Some good ideas but important mistakes → start with: Nice work —\n"
        "  • Mostly off-track but serious attempt → start with: Good effort —\n"
        "  • The approach needs rebuilding but they tried → start with: Let's build on this —\n"
        "  • If no meaningful written work is visible, or the page is too unreadable to infer a real approach, do NOT use praise-heavy openers like `Excellent —`, `Great job —`, or `Nice work —`. In that case use only a gentle neutral opener such as `Let's build on this —` or `Thanks for sharing your work —`, then kindly explain that there is not enough readable work to assess yet.\n"
        "- Strong praise must be earned by evidence on the page. Never say `Excellent`, `Great job`, or similar if the writing is blank, off-frame, or unreadable.\n"
        "- If the page is unreadable but the student clearly attempted the task, be kind and encouraging without overstating success: acknowledge the effort, say what could not be read, and suggest a clearer retake or next step.\n"
        "- After the opener, you may be honest about gaps: frame them as the next learning step, not as judgment on the person.\n\n"
        "Mathematics in the student-facing markdown (and only there; JSON values stay plain text):\n"
        "- The app renders markdown with KaTeX. Use ONLY inline `$...$` or display `$$...$$` for math.\n"
        "- Use standard LaTeX inside delimiters (e.g. `\\frac{a}{b}`, `\\sqrt{x}`, `\\cdot`, subscripts `x_1`).\n"
        "- Do NOT use `\\( ... \\)` or `\\[ ... \\]`; do not leave bare `^` or `_` outside math delimiters.\n"
        "- Avoid Unicode-only math glyphs as a substitute for LaTeX; prefer proper delimited expressions.\n\n"
        "Important — when to mention a retake (be conservative; false alarms upset students):\n"
        "- Default: grade whatever work is visible. Most photos are good enough — do **not** tell the student to retake because of mild blur, glare, shadows, or compression if equations, words, or standard notation (e.g. `n!`, fractions) are still readable.\n"
        "- Mention a clearer retake **only** when the image clearly fails as homework: no paper or no written attempt visible, the frame is the wrong subject (e.g. only a face or ceiling), or the writing is so unreadable that you cannot infer any approach. If part of the solution is visible, give substantive feedback on that part; at most add one gentle optional tip for lighting or distance next time — do not refuse to engage with readable work.\n"
        "- Do NOT guess rubric coverage for portions you truly cannot read.\n\n"
        "Output TWO things in this strict order:\n"
        "1) A single JSON object (machine-readable). Prefer raw JSON with NO markdown code fence. Keys:\n"
        "   - summary: one short sentence; warm and specific (not a cold verdict).\n"
        "   - rubric: array of {item, status: Met|Partial|Missing, evidence}; "
        "write each `evidence` line in neutral, kind language (what you noticed on the page, not a rebuke).\n"
        "   - correctness: Correct|Partially correct|Incorrect|Unclear (use Unclear only for illegible/off-topic/ambiguous work — not for short but valid notation.)\n"
        "   - key_mistakes: array of strings phrased as gentle \"things to watch\" or \"next checks\" — never insulting; keep each string short.\n"
        "   - next_steps: array of strings; each should sound helpful and doable (small wins), not overwhelming.\n"
        "   - clarifying_questions: array of strings (use [] when the answer is readable and unambiguous, including correct `n!`-style answers.)\n"
        "2) A blank line, then markdown for the student beginning with a heading exactly: ## Student feedback\n"
        "   - Write polished prose (short paragraphs and/or bullets). This is what the student reads in the app.\n"
        "   - Do NOT paste JSON, code fences, schema snippets, or key-value dumps into this markdown section.\n"
        "   - Do NOT wrap the student section in ``` fences of any kind.\n"
        "   - **Ask me anything** on this page: The study screen has a tutor chat launched from the **Ask me anything** button. "
        "Whenever your feedback suggests something that would naturally continue as a **conversation** or **live walkthrough** "
        "(e.g. \"we can practice...\", \"let's work through...\", \"if you want to explore...\", \"feel free to ask...\", "
        "or you invite follow-up questions or interactive rehearsal), add **one** short closing sentence telling them they can do that in "
        "**Ask me anything** on this same page (use that exact wording so it matches the button). "
        "Skip this add-on when everything you said is already self-contained and does not invite back-and-forth.\n"
    )

    content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    for p in image_paths:
        content.append({"type": "input_image", "image_url": _image_to_data_url(p)})

    resp = client.responses.create(
        model=model_name,
        input=[{"role": "user", "content": content}],
    )

    # Extract full text output.
    text = ""
    try:
        text = resp.output_text or ""
    except Exception:
        # Defensive fallback for any SDK response-shape changes.
        text = str(resp)

    parsed, md = _extract_json_and_markdown(text)
    if not md.strip():
        # Prefer the student section when present; never show the raw JSON preamble.
        if _STUDENT_FEEDBACK_HEADING_RE.search(text):
            md = _extract_student_feedback_section(text)
        else:
            md = _strip_leading_json_runs((text or "").strip())
    if not parsed:
        parsed = {"summary": "Unparsed response", "raw": (text or "").strip()}

    md = sanitize_student_feedback_markdown(md)

    return PaperFeedback(md=md.strip(), json=parsed)

