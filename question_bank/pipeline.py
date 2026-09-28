from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


STAGES = [
    "ingest",
    "chunk",
    "embed",
    "retrieve",
    "generate",
    "evaluate",
    "hints",
    "export",
]


def _idx(name: str) -> int:
    try:
        return STAGES.index(name)
    except ValueError as e:
        raise SystemExit(f"Unknown stage {name!r}; choose from {STAGES}") from e


def run_stage(stage: str, course: str, extra: list[str]) -> None:
    mod = {
        "ingest": "question_bank.ingest",
        "chunk": "question_bank.chunk",
        "embed": "question_bank.embed",
        "retrieve": "question_bank.retrieve_topics",
        "generate": "question_bank.generate_questions",
        "evaluate": "question_bank.evaluate_questions",
        "hints": "question_bank.backfill_hints",
        "export": "question_bank.export",
    }[stage]
    cmd = [sys.executable, "-m", mod, "--course", course, *extra]
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(Path(__file__).resolve().parent.parent))


def main() -> None:
    p = argparse.ArgumentParser(description="Run question bank stages in order")
    p.add_argument("--course", required=True)
    p.add_argument(
        "--from",
        dest="from_stage",
        default="ingest",
        choices=STAGES,
        help="Start at this stage",
    )
    p.add_argument(
        "--through",
        default="retrieve",
        choices=STAGES,
        help="Stop after this stage (inclusive)",
    )
    p.add_argument("--ingest-only", default=None, metavar="SUBDIR", help="Pass --only to ingest")
    p.add_argument("--force-embed", action="store_true", help="Pass --force to embed")
    p.add_argument(
        "--topics-yaml",
        type=Path,
        default=None,
        help="Passed to retrieve_topics",
    )
    p.add_argument(
        "--export-out",
        type=Path,
        default=None,
        help="Passed to export (exam JSON path)",
    )
    p.add_argument(
        "--base-url",
        default=None,
        help="If set with --upload, run upload_backend after export",
    )
    p.add_argument("--upload", action="store_true")
    p.add_argument(
        "--num-questions",
        type=int,
        default=None,
        metavar="N",
        help="Forwarded to generate_questions (e.g. 2 for a small test)",
    )
    p.add_argument(
        "--reasoning-effort",
        default=None,
        choices=["low", "medium", "high", "xhigh"],
        help="Forwarded to generate_questions for GPT-5 models",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=None,
        metavar="N",
        help="Forwarded to generate_questions (questions per API call; avoids huge JSON truncation)",
    )
    args = p.parse_args()

    lo, hi = _idx(args.from_stage), _idx(args.through)
    if hi < lo:
        raise SystemExit("--through must be >= --from")

    for stage in STAGES[lo : hi + 1]:
        extra: list[str] = []
        if stage == "ingest" and args.ingest_only:
            extra += ["--only", args.ingest_only]
        if stage == "embed" and args.force_embed:
            extra.append("--force")
        if stage == "retrieve" and args.topics_yaml:
            extra += ["--topics-yaml", str(args.topics_yaml)]
        if stage == "generate" and args.num_questions is not None:
            extra += ["--num-questions", str(args.num_questions)]
        if stage == "generate" and args.reasoning_effort is not None:
            extra += ["--reasoning-effort", args.reasoning_effort]
        if stage == "generate" and args.batch_size is not None:
            extra += ["--batch-size", str(args.batch_size)]
        if stage == "export" and args.export_out:
            extra += ["--out", str(args.export_out)]
        run_stage(stage, args.course, extra)

    if args.upload and _idx(args.through) >= _idx("export"):
        upload_extra: list[str] = ["--course", args.course]
        if args.base_url:
            upload_extra += ["--base-url", args.base_url]
        cmd = [sys.executable, "-m", "question_bank.upload_backend", *upload_extra]
        print("+", " ".join(cmd))
        subprocess.check_call(cmd, cwd=str(Path(__file__).resolve().parent.parent))


if __name__ == "__main__":
    main()
