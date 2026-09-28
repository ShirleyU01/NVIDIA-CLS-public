from __future__ import annotations

import argparse
import json
from pathlib import Path

from question_bank.chunking_rules import chunk_parsed_document
from question_bank.paths import chunks_jsonl_path, parsed_dir, repo_root
from question_bank.schemas import ParsedDocument


def load_parsed_docs_for_course(course: str) -> list[ParsedDocument]:
    out: list[ParsedDocument] = []
    for path in sorted(parsed_dir().glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("course") != course:
            continue
        out.append(ParsedDocument.model_validate(data))
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Job B: parsed JSON → chunks JSONL")
    p.add_argument("--course", required=True)
    args = p.parse_args()

    docs = load_parsed_docs_for_course(args.course)
    if not docs:
        print(f"No parsed documents for course={args.course} under {parsed_dir()}")
        raise SystemExit(1)

    out_path = chunks_jsonl_path(args.course)
    n = 0
    with out_path.open("w", encoding="utf-8") as f:
        for doc in docs:
            for chunk in chunk_parsed_document(doc):
                f.write(chunk.model_dump_json() + "\n")
                n += 1
    print(f"wrote {n} chunks → {out_path.relative_to(repo_root())}")


if __name__ == "__main__":
    main()
