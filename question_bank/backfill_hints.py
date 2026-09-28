from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from question_bank.generate_questions import _one_completion
from question_bank.paths import final_bank_dir, generated_dir, repo_root, topics_config_path
from question_bank.topics_config import load_topics_config


def _topic_label(raw: str) -> str:
    return (raw or "this topic").replace("_", " ").strip() or "this topic"


def _first_hint(question_type: str, topic_id: str) -> str:
    qtype = (question_type or "").lower()
    topic = _topic_label(topic_id)
    if "comput" in qtype:
        return "Start by naming the relevant quantities and writing the relationship before substituting values."
    if "misconception" in qtype:
        return f"Identify the claim being made, then compare it against the formal definition from {topic}."
    if "applied" in qtype or "scenario" in qtype:
        return "Translate the story into events, variables, or assumptions before trying to calculate or conclude anything."
    return f"Focus first on the central definition or representation from {topic}; avoid jumping straight to a final statement."


def _second_hint(item: dict[str, Any]) -> str:
    rubric = item.get("rubric") if isinstance(item.get("rubric"), dict) else {}
    mistakes = [
        str(x).strip().rstrip(".")
        for x in (rubric.get("common_mistakes") or [])
        if str(x).strip()
    ]
    if mistakes:
        return f"Watch out for this common trap: {mistakes[0]}. Decide what the correct setup should do differently."
    partial = [
        str(x).strip().rstrip(".")
        for x in (rubric.get("partial_credit") or [])
        if str(x).strip()
    ]
    if partial:
        return f"A partial solution often stops at: {partial[0]}. Add the missing reasoning or interpretation step."
    return "After setting up the problem, check which assumptions are being used and whether the conditioning or comparison changes the sample space."


def _third_hint(question_type: str) -> str:
    qtype = (question_type or "").lower()
    if "comput" in qtype:
        return "Once the setup is correct, carry the calculation through in small steps and interpret what the result means in the original context."
    if "misconception" in qtype:
        return "Use the formal test or definition to separate what feels intuitive from what is actually implied."
    if "applied" in qtype or "scenario" in qtype:
        return "Connect each term in your formula or explanation back to the real-world role it plays in the scenario."
    return "Finish by explaining why the definition applies here, not just by naming the definition."


def build_hints(item: dict[str, Any], fallback_topic_id: str) -> list[str]:
    topic_id = str(item.get("topic_id") or fallback_topic_id)
    question_type = str(item.get("question_type") or "")
    return [
        _first_hint(question_type, topic_id),
        _second_hint(item),
        _third_hint(question_type),
    ]


def _rubric_summary(item: dict[str, Any]) -> dict[str, list[str]]:
    rubric = item.get("rubric") if isinstance(item.get("rubric"), dict) else {}
    return {
        "full_credit": [str(x).strip() for x in rubric.get("full_credit") or [] if str(x).strip()],
        "partial_credit": [str(x).strip() for x in rubric.get("partial_credit") or [] if str(x).strip()],
        "common_mistakes": [str(x).strip() for x in rubric.get("common_mistakes") or [] if str(x).strip()],
    }


def _build_llm_prompt(
    item: dict[str, Any],
    *,
    course: str,
    fallback_topic_id: str,
    topic_names: dict[str, str],
) -> str:
    topic_id = str(item.get("topic_id") or fallback_topic_id)
    payload = {
        "course": course,
        "topic_id": topic_id,
        "topic_name": topic_names.get(topic_id) or _topic_label(topic_id),
        "question_type": str(item.get("question_type") or ""),
        "difficulty": str(item.get("difficulty") or ""),
        "question": str(item.get("question") or "").strip(),
        "expected_answer_for_authoring_only": str(item.get("expected_answer") or "").strip(),
        "rubric": _rubric_summary(item),
    }
    return f"""Write exactly three progressive hints for this study-mode question.

Return only valid JSON with this structure:
{{"hints": ["...", "...", "..."]}}

Hint quality rules:
- Hint 1 should be a gentle nudge about the concept, representation, or first thing to notice.
- Hint 2 should give more specific direction about setup, definitions, or quantities to identify.
- Hint 3 can point to the key relationship or next move, but must still avoid giving the final answer.
- Do not reveal final numeric values, final classifications, or complete final conclusions.
- Do not simply restate the question.
- Keep each hint concise: one or two sentences.
- Ground the hints in the question, expected answer, and rubric.

Question data:
{json.dumps(payload, indent=2)}
"""


def _model_from_config(course: str) -> str:
    cfg_path = topics_config_path(course)
    if cfg_path.exists():
        cfg = load_topics_config(cfg_path)
        return os.environ.get("QUESTION_BANK_GENERATION_MODEL", cfg.generation_model)
    return os.environ.get("QUESTION_BANK_GENERATION_MODEL", "gpt-5.4")


def _topic_names_from_config(course: str) -> dict[str, str]:
    cfg_path = topics_config_path(course)
    if not cfg_path.exists():
        return {}
    cfg = load_topics_config(cfg_path)
    return {topic.id: topic.name for topic in cfg.topics}


def build_hints_with_llm(
    item: dict[str, Any],
    *,
    client: OpenAI,
    course: str,
    fallback_topic_id: str,
    topic_names: dict[str, str],
    model: str,
    reasoning_effort: str,
) -> list[str]:
    base_prompt = _build_llm_prompt(
        item,
        course=course,
        fallback_topic_id=fallback_topic_id,
        topic_names=topic_names,
    )
    last_count = 0
    for attempt in range(2):
        user = base_prompt
        if attempt:
            user += (
                "\nYour previous response did not contain exactly three non-empty hints. "
                "Return exactly three strings in the JSON hints array."
            )
        raw = _one_completion(
            client,
            model=model,
            system=(
                "You write high-quality educational hints for university probability and statistics "
                "practice questions. Help without solving the problem outright."
            ),
            user=user,
            max_completion_tokens=900,
            reasoning_effort=reasoning_effort,
        )
        hints = _normalize_existing_hints(raw.get("hints"))
        last_count = len(hints)
        if len(hints) == 3:
            return hints
    raise ValueError(f"LLM returned {last_count} hints, expected 3")


def _normalize_existing_hints(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()]


def _update_question(
    item: Any,
    fallback_topic_id: str,
    *,
    overwrite: bool,
    llm_options: dict[str, Any] | None = None,
) -> bool:
    if not isinstance(item, dict):
        return False
    existing = _normalize_existing_hints(item.get("hints"))
    if len(existing) == 3 and not overwrite:
        item["hints"] = existing
        return False
    if llm_options:
        item["hints"] = build_hints_with_llm(
            item,
            fallback_topic_id=fallback_topic_id,
            **llm_options,
        )
    else:
        item["hints"] = build_hints(item, fallback_topic_id)
    return True


def backfill_file(
    path: Path,
    *,
    overwrite: bool,
    llm_options: dict[str, Any] | None = None,
    remaining: int | None = None,
) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    if isinstance(data, dict) and isinstance(data.get("questions"), list):
        fallback_topic_id = str(data.get("topic_id") or path.stem)
        for item in data["questions"]:
            if remaining is not None and changed >= remaining:
                break
            if _update_question(
                item,
                fallback_topic_id,
                overwrite=overwrite,
                llm_options=llm_options,
            ):
                changed += 1
    elif isinstance(data, list):
        for item in data:
            if remaining is not None and changed >= remaining:
                break
            if _update_question(
                item,
                path.stem,
                overwrite=overwrite,
                llm_options=llm_options,
            ):
                changed += 1
    if changed:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return changed


def _target_dirs(course: str, target: str) -> list[Path]:
    dirs: list[Path] = []
    if target in ("generated", "both"):
        dirs.append(generated_dir(course))
    if target in ("final", "both"):
        dirs.append(final_bank_dir(course))
    return dirs


def main() -> None:
    p = argparse.ArgumentParser(
        description="Add three progressive hints to existing generated/final question-bank JSON files."
    )
    p.add_argument("--course", required=True)
    p.add_argument(
        "--target",
        choices=["generated", "final", "both"],
        default="final",
        help="Which question-bank checkpoint to update (default: final).",
    )
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenerate hints even when a question already has three hints.",
    )
    p.add_argument(
        "--mode",
        choices=["template", "llm"],
        default="template",
        help="Use deterministic templates or call the configured generation LLM.",
    )
    p.add_argument(
        "--model",
        default=None,
        help="LLM model for --mode llm (default: QUESTION_BANK_GENERATION_MODEL or course config).",
    )
    p.add_argument(
        "--reasoning-effort",
        default=os.environ.get("QUESTION_BANK_REASONING_EFFORT", "medium"),
        choices=["low", "medium", "high", "xhigh"],
        help="Reasoning effort for GPT-5 hint generation.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Update at most N questions, useful for testing LLM hint quality.",
    )
    p.add_argument(
        "--topic",
        action="append",
        default=None,
        metavar="TOPIC_ID",
        help="Only update this topic file. Can be passed multiple times.",
    )
    args = p.parse_args()

    llm_options: dict[str, Any] | None = None
    if args.mode == "llm":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        model = args.model or _model_from_config(args.course)
        llm_options = {
            "client": OpenAI(api_key=api_key),
            "course": args.course,
            "topic_names": _topic_names_from_config(args.course),
            "model": model,
            "reasoning_effort": args.reasoning_effort,
        }
        print(f"using LLM hint model: {model}")

    total_files = 0
    total_questions = 0
    topic_filter = set(args.topic or [])
    for directory in _target_dirs(args.course, args.target):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            if path.name in {"export_exam.json", "evaluation_log.jsonl", "merged_bank.json"}:
                continue
            if topic_filter and path.stem not in topic_filter:
                continue
            remaining = None if args.limit is None else max(args.limit - total_questions, 0)
            if remaining == 0:
                break
            changed = backfill_file(
                path,
                overwrite=args.overwrite,
                llm_options=llm_options,
                remaining=remaining,
            )
            if changed:
                total_files += 1
                total_questions += changed
                print(f"updated {path.relative_to(repo_root())} ({changed} questions)")
        if args.limit is not None and total_questions >= args.limit:
            break
    print(f"backfilled {total_questions} questions across {total_files} files")


if __name__ == "__main__":
    main()
