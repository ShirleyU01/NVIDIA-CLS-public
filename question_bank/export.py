from __future__ import annotations

import argparse
import json
from pathlib import Path

from question_bank.paths import final_bank_dir, repo_root
from question_bank.schemas import CanonicalQuestion, RubricCanonical


def flatten_rubric(r: RubricCanonical) -> list[str]:
    items: list[str] = []
    if r.full_credit:
        items.append("Full credit: " + "; ".join(r.full_credit))
    if r.partial_credit:
        items.append("Partial credit: " + "; ".join(r.partial_credit))
    if r.common_mistakes:
        items.append("Common mistakes: " + "; ".join(r.common_mistakes))
    if not items:
        items = ["Demonstrates understanding of the topic with clear reasoning."]
    return items


def main() -> None:
    p = argparse.ArgumentParser(description="Export validated bank → proctor exam JSON + merged_bank.json")
    p.add_argument("--course", required=True)
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Exam JSON output path (default: question_bank_data/final_question_bank/<course>/export_exam.json)",
    )
    p.add_argument("--exam-id", default=None)
    p.add_argument("--subject", default=None)
    p.add_argument("--system-prompt", default="You are an oral exam proctor for a university course.")
    p.add_argument("--max-follow-ups", type=int, default=2)
    p.add_argument("--post-exam-follow-ups", type=int, default=2)
    args = p.parse_args()

    bank_dir = final_bank_dir(args.course)
    merged: list[CanonicalQuestion] = []
    for path in sorted(bank_dir.glob("*.json")):
        if path.name in ("merged_bank.json", "export_exam.json", "evaluation_log.jsonl"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for raw in data.get("questions") or []:
            try:
                merged.append(CanonicalQuestion.model_validate(raw))
            except Exception:
                continue

    merged_path = bank_dir / "merged_bank.json"
    merged_path.write_text(
        json.dumps([q.model_dump() for q in merged], indent=2),
        encoding="utf-8",
    )

    subject = args.subject or f"{args.course} oral question bank"
    exam_id = args.exam_id or f"{args.course.lower()}_question_bank_export"
    questions_out = []
    for q in merged:
        questions_out.append(
            {
                "id": q.question_id,
                "text": q.question,
                "rubric_items": flatten_rubric(q.rubric),
                "max_follow_ups": args.max_follow_ups,
            }
        )

    exam = {
        "exam_id": exam_id,
        "title": subject,
        "subject": subject,
        "system_prompt": args.system_prompt,
        "post_exam_follow_ups": args.post_exam_follow_ups,
        "questions": questions_out,
    }

    out = args.out or (bank_dir / "export_exam.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(exam, indent=2), encoding="utf-8")
    print(f"wrote {out.relative_to(repo_root())} ({len(questions_out)} questions)")
    print(f"wrote {merged_path.relative_to(repo_root())} ({len(merged)} canonical)")


if __name__ == "__main__":
    main()
