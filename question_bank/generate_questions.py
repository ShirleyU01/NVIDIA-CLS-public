from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import yaml
from openai import OpenAI

from question_bank.latex_validation import latex_issues
from question_bank.paths import configs_dir, generated_dir, repo_root, topic_contexts_dir, topics_config_path
from question_bank.schemas import (
    CanonicalQuestion,
    FollowUpCanonical,
    RubricCanonical,
    TopicContextBundle,
)
from question_bank.topics_config import load_topics_config


def _load_system_prompt() -> str:
    p = configs_dir() / "prompts.yaml"
    if not p.exists():
        return (
            "You write oral exam questions grounded in the provided context. "
            "Return only valid JSON with key questions (array)."
        )
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and raw.get("generation_system"):
        return str(raw["generation_system"]).strip()
    return (
        "You write oral exam questions grounded in the provided context. "
        "Return only valid JSON with key questions (array)."
    )


def _context_blocks(bundle: TopicContextBundle, max_chars: int = 28000) -> str:
    parts: list[str] = []
    n = 0
    for c in bundle.chunks:
        block = f"[{c.chunk_id}]\n{c.text.strip()}\n"
        if n + len(block) > max_chars:
            break
        parts.append(block)
        n += len(block)
    return "\n".join(parts)


def _build_user_prompt(
    bundle: TopicContextBundle,
    num_questions: int,
    *,
    batch_index: int = 0,
    total_batches: int = 1,
) -> str:
    ctx = _context_blocks(bundle)
    batch_note = ""
    if total_batches > 1:
        batch_note = (
            f"\nThis is batch {batch_index + 1} of {total_batches}. "
            f"Write exactly {num_questions} NEW questions (no duplicates vs prior batches). "
            "Vary scenarios and wording.\n"
        )
    return f"""Topic id: {bundle.topic_id}
Topic name: {bundle.topic_name}

Context (each block starts with a chunk id in square brackets on its own line):
{ctx}
{batch_note}

Task: Write exactly {num_questions} substantive oral-exam questions. Mix types:
conceptual_depth, computational_reasoning, misconception_check, applied_scenario.
Vary difficulty among medium and hard; use easy only when the topic genuinely
requires a foundational warm-up.

Return JSON with this structure (types as strings):
{{
  "questions": [
    {{
      "question_type": "conceptual",
      "difficulty": "easy",
      "question": "...",
      "expected_answer": "...",
      "source_chunk_ids": ["paste_chunk_ids_from_brackets_above"],
      "hints": [
        "Hint 1: a gentle nudge about the first concept or representation to use.",
        "Hint 2: a more specific setup step, definition, or quantity to identify.",
        "Hint 3: the key relationship or next move, without stating the final answer."
      ],
      "rubric": {{
        "full_credit": ["..."],
        "partial_credit": ["..."],
        "common_mistakes": ["..."]
      }},
      "follow_ups": [
        {{"condition": "correct", "question": "..."}},
        {{"condition": "incorrect", "question": "..."}}
      ]
    }}
  ]
}}

Rules:
- source_chunk_ids must match bracket headers exactly.
- Avoid one-sentence definition questions unless they require comparison,
  justification, or application.
- Each question should normally be 2-4 sentences or include a concrete scenario.
- Expected answers should include the reasoning steps a strong student should say aloud.
- Provide exactly three hints per question, ordered from least revealing to most revealing.
- Hints should help a stuck student choose a representation, recall a relevant definition,
  or identify the next step. Do not state the final answer or simply restate the question.
- Computational questions should require setup and interpretation, not just arithmetic.
- Follow-ups should probe reasoning, assumptions, or common mistakes.
- If context is thin, ask high-level reasoning questions grounded in the available
  context rather than inventing unsupported details.
- Math notation must be KaTeX-safe. Put every math expression inside `$...$` or
  `$$...$$`; never use `\\(...\\)` or `\\[...\\]`; never write bare `^` or `_`
  outside math delimiters; use fully braced commands such as `$\\frac{{a}}{{b}}$`,
  `$\\sqrt{{x}}$`, and `$\\binom{{10}}{{3}}$` (not `\\binom103`).
"""


def _question_latex_issues(q: CanonicalQuestion) -> list[str]:
    checks: list[tuple[str, str]] = [
        ("question", q.question),
        ("expected_answer", q.expected_answer),
    ]
    checks.extend((f"hint[{i}]", h) for i, h in enumerate(q.hints))
    checks.extend((f"rubric.full_credit[{i}]", item) for i, item in enumerate(q.rubric.full_credit))
    checks.extend((f"rubric.partial_credit[{i}]", item) for i, item in enumerate(q.rubric.partial_credit))
    checks.extend((f"rubric.common_mistakes[{i}]", item) for i, item in enumerate(q.rubric.common_mistakes))
    checks.extend((f"follow_ups[{i}].question", fu.question) for i, fu in enumerate(q.follow_ups))

    issues: list[str] = []
    for field, text in checks:
        for issue in latex_issues(text):
            issues.append(f"{field}:{issue}")
    return issues


def _parse_questions(
    raw: dict,
    *,
    course: str,
    topic_id: str,
    id_offset: int = 0,
) -> list[CanonicalQuestion]:
    arr = raw.get("questions")
    if not isinstance(arr, list):
        return []
    out: list[CanonicalQuestion] = []
    for i, item in enumerate(arr, start=1):
        if not isinstance(item, dict):
            continue
        qid = str(
            item.get("question_id")
            or f"{course}_{topic_id}_{id_offset + i:04d}"
        )
        hints = [str(x).strip() for x in (item.get("hints") or []) if str(x).strip()]
        rub = item.get("rubric") or {}
        rc = RubricCanonical(
            full_credit=list(rub.get("full_credit") or []),
            partial_credit=list(rub.get("partial_credit") or []),
            common_mistakes=list(rub.get("common_mistakes") or []),
        )
        fus = []
        for fu in item.get("follow_ups") or []:
            if isinstance(fu, dict) and fu.get("question"):
                fus.append(
                    FollowUpCanonical(
                        condition=str(fu.get("condition") or "any"),
                        question=str(fu["question"]),
                    )
                )
        try:
            cq = CanonicalQuestion(
                question_id=qid,
                course=course,
                topic_id=topic_id,
                question_type=str(item.get("question_type") or "conceptual"),
                difficulty=str(item.get("difficulty") or "medium"),
                question=str(item.get("question") or "").strip(),
                expected_answer=str(item.get("expected_answer") or "").strip(),
                source_chunk_ids=[str(x) for x in (item.get("source_chunk_ids") or [])],
                hints=hints,
                rubric=rc,
                follow_ups=fus,
            )
        except Exception:
            continue
        if cq.question and cq.expected_answer and not _question_latex_issues(cq):
            out.append(cq)
    return out


def _strip_json_fence(s: str) -> str:
    s = s.strip()
    m = re.match(r"^```(?:json)?\s*([\s\S]*?)```$", s)
    if m:
        return m.group(1).strip()
    return s


def _uses_responses_api(model: str) -> bool:
    return model.startswith("gpt-5")


def _extract_response_text(resp: object) -> str:
    output_text = getattr(resp, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    # Fallback for SDKs that expose Responses output as typed content blocks.
    parts: list[str] = []
    for item in getattr(resp, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts).strip()


def _default_batch_size() -> int:
    raw = os.environ.get("QUESTION_BANK_GEN_BATCH_SIZE", "20").strip()
    try:
        n = int(raw)
        return max(1, min(n, 50))
    except ValueError:
        return 20


def _one_completion(
    client: OpenAI,
    *,
    model: str,
    system: str,
    user: str,
    max_completion_tokens: int,
    reasoning_effort: str,
) -> dict:
    if _uses_responses_api(model):
        response_args = {
            "model": model,
            "reasoning": {"effort": reasoning_effort},
            "max_output_tokens": max_completion_tokens,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            resp = client.responses.create(
                **response_args,
                text={"format": {"type": "json_object"}},
            )
        except Exception as e:
            if "json_object" not in str(e):
                raise
            resp = client.responses.create(
                **response_args,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "questions_json",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "questions": {
                                    "type": "array",
                                    "items": {"type": "object"},
                                }
                            },
                            "required": ["questions"],
                            "additionalProperties": False,
                        },
                    }
                },
            )
        text = _extract_response_text(resp)
        text = _strip_json_fence(text)
        return json.loads(text)

    kwargs = dict(
        model=model,
        temperature=0.35,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    try:
        resp = client.chat.completions.create(
            **kwargs, max_completion_tokens=max_completion_tokens
        )
    except TypeError:
        resp = client.chat.completions.create(**kwargs, max_tokens=max_completion_tokens)
    text = (resp.choices[0].message.content or "").strip()
    text = _strip_json_fence(text)
    return json.loads(text)


def generate_for_topic(
    bundle: TopicContextBundle,
    *,
    course: str,
    num_questions: int,
    model: str,
    reasoning_effort: str,
    batch_size: int | None = None,
) -> list[CanonicalQuestion]:
    """
    Generate questions in batches. A single API call for ~100 long JSON items often
    truncates (invalid JSON / Unterminated string); batching avoids that.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    bs = batch_size if batch_size is not None else _default_batch_size()
    if num_questions <= 0:
        return []

    client = OpenAI(api_key=api_key)
    system = _load_system_prompt()

    # Plan batch sizes (last batch may be smaller)
    remaining = num_questions
    sizes: list[int] = []
    while remaining > 0:
        take = min(bs, remaining)
        sizes.append(take)
        remaining -= take

    all_q: list[CanonicalQuestion] = []
    total_batches = len(sizes)
    # Tokens per batch: small batches need less ceiling; cap avoids API errors on tiny models
    per_batch_cap = min(16384, 2000 + sizes[0] * 450)

    for bi, n in enumerate(sizes):
        user = _build_user_prompt(
            bundle, n, batch_index=bi, total_batches=total_batches
        )
        raw = _one_completion(
            client,
            model=model,
            system=system,
            user=user,
            max_completion_tokens=per_batch_cap,
            reasoning_effort=reasoning_effort,
        )
        batch_qs = _parse_questions(
            raw,
            course=course,
            topic_id=bundle.topic_id,
            id_offset=len(all_q),
        )
        all_q.extend(batch_qs)

    return all_q


def main() -> None:
    p = argparse.ArgumentParser(description="Job E: topic bundles → draft questions JSON")
    p.add_argument("--course", required=True)
    p.add_argument("--topic", default=None, help="Single topic id; default all in topics yaml")
    p.add_argument("--num-questions", type=int, default=8)
    p.add_argument(
        "--reasoning-effort",
        default=os.environ.get("QUESTION_BANK_REASONING_EFFORT", "medium"),
        choices=["low", "medium", "high", "xhigh"],
        help="Reasoning effort for GPT-5 generation models",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=None,
        metavar="N",
        help="Questions per API call (default env QUESTION_BANK_GEN_BATCH_SIZE or 20). "
        "Lower if JSON still truncates.",
    )
    p.add_argument("--topics-yaml", type=Path, default=None)
    args = p.parse_args()

    cfg_path = args.topics_yaml or topics_config_path(args.course)
    if not cfg_path.exists():
        print(f"Missing {cfg_path}")
        raise SystemExit(1)
    cfg = load_topics_config(cfg_path)
    model = os.environ.get("QUESTION_BANK_GENERATION_MODEL", cfg.generation_model)

    ctx_dir = topic_contexts_dir(args.course)
    out_dir = generated_dir(args.course)
    topic_ids = [t.id for t in cfg.topics]
    if args.topic:
        topic_ids = [args.topic]

    for tid in topic_ids:
        bundle_path = ctx_dir / f"{tid}.json"
        if not bundle_path.exists():
            print(f"skip (no bundle): {bundle_path}")
            continue
        bundle = TopicContextBundle.model_validate_json(
            bundle_path.read_text(encoding="utf-8")
        )
        if not bundle.chunks:
            print(f"skip (empty chunks): {tid}")
            continue
        try:
            qs = generate_for_topic(
                bundle,
                course=args.course,
                num_questions=args.num_questions,
                model=model,
                reasoning_effort=args.reasoning_effort,
                batch_size=args.batch_size,
            )
        except Exception as e:
            print(f"ERROR {tid}: {e}")
            raise SystemExit(1) from e
        payload = {
            "topic_id": tid,
            "topic_name": bundle.topic_name,
            "course": args.course,
            "model": model,
            "questions": [q.model_dump() for q in qs],
        }
        out_path = out_dir / f"{tid}.json"
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote {out_path.relative_to(repo_root())} ({len(qs)} questions)")


if __name__ == "__main__":
    main()
