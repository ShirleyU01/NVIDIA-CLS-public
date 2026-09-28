from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from question_bank.latex_validation import latex_issues
from question_bank.paths import final_bank_dir, generated_dir, repo_root
from question_bank.schemas import CanonicalQuestion


BASIC_RECALL_PATTERNS = [
    re.compile(r"^\s*what is the definition of\b", re.I),
    re.compile(r"^\s*define\b", re.I),
    re.compile(r"^\s*what does .+ mean\b", re.I),
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().strip())


def evaluate_one(q: CanonicalQuestion) -> tuple[bool, list[str]]:
    issues: list[str] = []
    question = q.question.strip()
    expected_answer = q.expected_answer.strip()
    is_basic_recall = any(p.search(question) for p in BASIC_RECALL_PATTERNS)
    latex_checks: list[str] = [question, expected_answer]
    latex_checks.extend(q.hints)
    latex_checks.extend(q.rubric.full_credit)
    latex_checks.extend(q.rubric.partial_credit)
    latex_checks.extend(q.rubric.common_mistakes)
    latex_checks.extend(fu.question for fu in q.follow_ups)

    if len(question) < 60:
        issues.append("question_too_short")
    if len(expected_answer) < 120:
        issues.append("expected_answer_too_short")
    if is_basic_recall:
        issues.append("basic_recall_question")
    if q.difficulty.lower() == "easy" and (len(question) < 100 or is_basic_recall):
        issues.append("easy_question_too_simple")
    if not q.rubric.full_credit:
        issues.append("missing_full_credit_rubric")
    if len(q.hints) != 3:
        issues.append("missing_three_hints")
    elif any(len(h.strip()) < 12 for h in q.hints):
        issues.append("hint_too_short")
    if len(q.follow_ups) < 2:
        issues.append("missing_follow_ups")
    if not q.source_chunk_ids:
        issues.append("missing_source_chunk_ids")
    latex_problem_types = sorted({issue for text in latex_checks for issue in latex_issues(text)})
    issues.extend(f"latex_{issue}" for issue in latex_problem_types)
    return (len(issues) == 0), issues


def main() -> None:
    p = argparse.ArgumentParser(description="Job F: filter generated questions → final bank")
    p.add_argument("--course", required=True)
    args = p.parse_args()

    gen_dir = generated_dir(args.course)
    out_dir = final_bank_dir(args.course)
    log_path = out_dir / "evaluation_log.jsonl"

    if not gen_dir.exists():
        print(f"No generated dir: {gen_dir}")
        raise SystemExit(1)

    seen_norm: set[str] = set()
    with log_path.open("w", encoding="utf-8") as log:
        for path in sorted(gen_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            topic_id = data.get("topic_id") or path.stem
            raw_qs = data.get("questions") or []
            kept: list[dict] = []
            for raw in raw_qs:
                try:
                    q = CanonicalQuestion.model_validate(raw)
                except Exception as e:
                    log.write(
                        json.dumps(
                            {"topic_id": topic_id, "ok": False, "error": str(e)}
                        )
                        + "\n"
                    )
                    continue
                ok, issues = evaluate_one(q)
                nq = _norm(q.question)
                dup = nq in seen_norm
                if dup:
                    issues.append("near_duplicate_text")
                    ok = False
                if ok:
                    seen_norm.add(nq)
                    kept.append(q.model_dump())
                log.write(
                    json.dumps(
                        {
                            "question_id": q.question_id,
                            "topic_id": topic_id,
                            "ok": ok,
                            "issues": issues,
                        }
                    )
                    + "\n"
                )
            out_path = out_dir / f"{topic_id}.json"
            out_payload = {
                "topic_id": topic_id,
                "topic_name": data.get("topic_name"),
                "course": args.course,
                "questions": kept,
            }
            out_path.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")
            print(f"wrote {out_path.relative_to(repo_root())} ({len(kept)} kept)")

    print(f"log: {log_path.relative_to(repo_root())}")


if __name__ == "__main__":
    main()
