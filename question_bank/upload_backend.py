from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None  # type: ignore

from question_bank.paths import configs_dir, final_bank_dir, repo_root


def main() -> None:
    p = argparse.ArgumentParser(
        description="POST rubric + question set + assessment to central backend (no auth; dev only)"
    )
    p.add_argument("--course", required=True)
    p.add_argument(
        "--base-url",
        default=os.environ.get("CENTRAL_API_BASE_URL", "http://127.0.0.1:8000"),
    )
    p.add_argument(
        "--exam-json",
        type=Path,
        default=None,
        help="Default: question_bank_data/final_question_bank/<course>/export_exam.json",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--assessment-title", default=None)
    args = p.parse_args()

    if requests is None:
        raise SystemExit("pip install requests")

    exam_path = args.exam_json or (final_bank_dir(args.course) / "export_exam.json")
    if not exam_path.exists():
        print(f"Missing exam JSON: {exam_path}")
        raise SystemExit(1)

    exam = json.loads(exam_path.read_text(encoding="utf-8"))
    rubric_path = configs_dir() / "oral_rubric_default.json"
    rubric_json = json.loads(rubric_path.read_text(encoding="utf-8"))

    base = args.base_url.rstrip("/")
    title = args.assessment_title or exam.get("title") or f"{args.course} question bank"

    rubric_payload = {
        "title": f"{title} (rubric)",
        "subject": args.course,
        "rubric_json": rubric_json,
    }
    qs_payload = {
        "title": f"{title} (questions)",
        "subject": args.course,
        "question_set_json": exam,
    }
    if args.dry_run:
        print(json.dumps({"rubric": rubric_payload, "question_set": qs_payload}, indent=2))
        return

    r1 = requests.post(f"{base}/rubrics", json=rubric_payload, timeout=60)
    r1.raise_for_status()
    rubric_id = r1.json()["id"]
    r2 = requests.post(f"{base}/question-sets", json=qs_payload, timeout=60)
    r2.raise_for_status()
    qs_id = r2.json()["id"]
    r3 = requests.post(
        f"{base}/assessments",
        json={
            "rubric_id": rubric_id,
            "question_set_id": qs_id,
            "title": title,
            "description": "Created by question_bank.upload_backend",
        },
        timeout=60,
    )
    r3.raise_for_status()
    aid = r3.json()["id"]
    print(f"rubric_id={rubric_id} question_set_id={qs_id} assessment_id={aid}")


if __name__ == "__main__":
    main()
