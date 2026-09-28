from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from question_bank.parse_pdf import extract_pdf_pages, title_guess_from_path
from question_bank.paths import parsed_dir, raw_course_dir, repo_root
from question_bank.schemas import ParsedDocument, ParsedPage, utc_now_iso


ROLE_BY_SUBDIR = {
    "lectures": "lecture",
    "exams": "exam",
    "solutions": "solution",
    "review": "review",
    "reviews": "review",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def output_slug(course: str, role: str, pdf_path: Path, raw_root: Path) -> str:
    rel = pdf_path.relative_to(raw_root)
    parent = rel.parent.name if len(rel.parts) > 1 else ""
    stem = _safe_stem(rel.stem)
    if parent and parent not in ROLE_BY_SUBDIR:
        return f"{course.lower()}_{role}_{parent}_{stem}"
    return f"{course.lower()}_{role}_{stem}"


def _safe_stem(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", s).strip("_")[:80] or "file"


def _normalize_only(only: str) -> str:
    o = only.lower().strip("/")
    aliases = {
        "lecture": "lectures",
        "exam": "exams",
        "exams": "exams",
        "solution": "solutions",
        "solutions": "solutions",
        "review": "review",
        "reviews": "reviews",
    }
    return aliases.get(o, o)


def discover_pdfs(course: str, only: str | None) -> list[tuple[Path, str]]:
    """Return list of (pdf_path, document_role)."""
    root = raw_course_dir(course)
    if not root.is_dir():
        return []
    want_sub: str | None = _normalize_only(only) if only else None
    out: list[tuple[Path, str]] = []
    for sub, role in ROLE_BY_SUBDIR.items():
        if want_sub and sub != want_sub:
            continue
        d = root / sub
        if not d.is_dir():
            continue
        for pdf in sorted(d.rglob("*.pdf")):
            out.append((pdf, role))
    return out


def ingest_one(
    pdf_path: Path,
    document_role: str,
    course: str,
    *,
    force: bool = False,
) -> Path | None:
    raw_root = raw_course_dir(course)
    rel = str(pdf_path.relative_to(repo_root()))
    digest = sha256_file(pdf_path)
    slug = output_slug(course, document_role, pdf_path, raw_root)
    out_path = parsed_dir() / f"{slug}.json"

    if out_path.exists() and not force:
        try:
            prev = json.loads(out_path.read_text(encoding="utf-8"))
            if prev.get("sha256") == digest:
                return None
        except (json.JSONDecodeError, OSError):
            pass

    pages_raw = extract_pdf_pages(pdf_path)
    pages = [ParsedPage(page_index=p.page_index, text=p.text) for p in pages_raw]
    doc = ParsedDocument(
        course=course,
        document_role=document_role,  # type: ignore[arg-type]
        source_path=rel,
        relative_path=rel,
        sha256=digest,
        title_guess=title_guess_from_path(pdf_path),
        pages=pages,
        ingested_at=utc_now_iso(),
    )
    out_path.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    return out_path


def main() -> None:
    p = argparse.ArgumentParser(description="Job A: ingest PDFs → question_bank_data/parsed/")
    p.add_argument("--course", required=True)
    p.add_argument(
        "--only",
        metavar="SUBDIR",
        help="Restrict to one raw subfolder: lectures, exams, solutions, review",
    )
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    items = discover_pdfs(args.course, args.only)
    if not items:
        print(f"No PDFs found under {raw_course_dir(args.course)}")
        raise SystemExit(1)
    written = 0
    skipped = 0
    for pdf, role in items:
        r = ingest_one(pdf, role, args.course, force=args.force)
        if r is None:
            skipped += 1
            print(f"skip (unchanged): {pdf.name}")
        else:
            written += 1
            print(f"wrote: {r.relative_to(repo_root())}")
    print(f"ingest done: {written} wrote, {skipped} skipped")


if __name__ == "__main__":
    main()
