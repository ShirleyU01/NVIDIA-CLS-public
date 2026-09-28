from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import List, Optional

from question_bank.schemas import ChunkRecord, ParsedDocument


def _slug(s: str) -> str:
    x = re.sub(r"[^a-zA-Z0-9]+", "_", s.strip().lower()).strip("_")
    return x or "doc"


def _short_role(document_role: str) -> str:
    return {"lecture": "lec", "exam": "exam", "solution": "sol", "review": "rev"}.get(
        document_role, "unk"
    )


def _chunk_id(course: str, parsed_slug: str, qual: str) -> str:
    qual_s = _slug(qual)[:48]
    raw = f"{course}|{parsed_slug}|{qual_s}".encode()
    h = hashlib.sha256(raw).hexdigest()[:10]
    base = _slug(f"{course}_{parsed_slug}_{qual_s}")[:72]
    return f"{base}_{h}"


def _source_type_for_role(role: str) -> str:
    return {
        "lecture": "lecture_slide",
        "exam": "exam_question",
        "solution": "exam_question",
        "review": "review_section",
        "unknown": "document",
    }.get(role, "document")


def chunk_lecture(
    doc: ParsedDocument,
    *,
    min_merge_chars: int = 120,
) -> List[ChunkRecord]:
    """One page per chunk; merge consecutive tiny pages."""
    course = doc.course
    parsed_slug = _slug(Path(doc.relative_path).stem)
    document_name = doc.title_guess
    out: List[ChunkRecord] = []
    buf_pages: list[int] = []
    buf_text: list[str] = []

    def flush() -> None:
        nonlocal buf_pages, buf_text
        if not buf_pages:
            return
        text = "\n\n".join(buf_text).strip()
        if not text:
            buf_pages, buf_text = [], []
            return
        p0, p1 = buf_pages[0], buf_pages[-1]
        qual = f"p{p0}" if p0 == p1 else f"p{p0}_p{p1}"
        out.append(
            ChunkRecord(
                chunk_id=_chunk_id(course, parsed_slug, qual),
                course=course,
                source_type="lecture_slide",
                document_name=document_name,
                source_path=doc.source_path,
                parsed_slug=parsed_slug,
                page_span=[p0, p1],
                question_id=None,
                text=text,
            )
        )
        buf_pages, buf_text = [], []

    for page in doc.pages:
        t = page.text.strip()
        if not buf_pages:
            buf_pages = [page.page_index]
            buf_text = [t]
            continue
        if len(t) < min_merge_chars:
            buf_pages.append(page.page_index)
            buf_text.append(t)
        else:
            flush()
            buf_pages = [page.page_index]
            buf_text = [t]
    flush()
    return out


def _split_exam_like_text(full_text: str) -> list[tuple[Optional[str], str]]:
    """
    Split into (question_id, body) blocks.
    Main questions: line starts with optional whitespace, digits, '.', optional space, rest.
    Subparts: line starts with (a) / (b) ... and attaches to new ids like '3a'.
    """
    lines = full_text.splitlines()
    blocks: list[tuple[Optional[str], str]] = []
    qid: Optional[str] = None
    acc: list[str] = []

    main_re = re.compile(r"^\s*(\d+)\.\s*(.*)$")
    sub_re = re.compile(r"^\s*\(([a-z])\)\s*(.*)$", re.IGNORECASE)

    def flush() -> None:
        nonlocal acc, qid
        body = "\n".join(acc).strip()
        if body:
            blocks.append((qid, body))
        acc = []

    for line in lines:
        mm = main_re.match(line)
        if mm:
            flush()
            qid = mm.group(1)
            rest = (mm.group(2) or "").strip()
            acc = [rest] if rest else []
            continue
        sm = sub_re.match(line)
        if sm and qid is not None:
            flush()
            sub_letter = sm.group(1).lower()
            mnum = re.match(r"^(\d+)", qid)
            if mnum:
                main = mnum.group(1)
                qid = f"{main}{sub_letter}"
            else:
                qid = f"{qid}{sub_letter}"
            rest = (sm.group(2) or "").strip()
            acc = [rest] if rest else []
            continue
        acc.append(line)
    flush()
    return blocks


def chunk_exam_like(doc: ParsedDocument) -> List[ChunkRecord]:
    """exam / solution: regex blocks; fallback to per-page if no numbered questions."""
    course = doc.course
    parsed_slug = _slug(Path(doc.relative_path).stem)
    document_name = doc.title_guess
    full_text = "\n\n".join(p.text for p in doc.pages if p.text.strip())
    stype = _source_type_for_role(doc.document_role)

    blocks = _split_exam_like_text(full_text)
    numbered = [b for b in blocks if b[0] is not None]
    if not numbered:
        return chunk_lecture(doc, min_merge_chars=0)

    last_pi = doc.pages[-1].page_index if doc.pages else 0
    out: List[ChunkRecord] = []
    for qid, body in blocks:
        if not body.strip():
            continue
        qual = f"q{qid}" if qid is not None else "preamble"
        out.append(
            ChunkRecord(
                chunk_id=_chunk_id(course, parsed_slug, qual),
                course=course,
                source_type=stype,
                document_name=document_name,
                source_path=doc.source_path,
                parsed_slug=parsed_slug,
                page_span=[0, last_pi],
                question_id=qid,
                text=body.strip(),
            )
        )
    return out


def chunk_review(doc: ParsedDocument, *, max_chars: int = 4000) -> List[ChunkRecord]:
    """Split on markdown-style # headings; subdivide long sections by paragraphs."""
    course = doc.course
    parsed_slug = _slug(Path(doc.relative_path).stem)
    document_name = doc.title_guess
    full_text = "\n\n".join(p.text for p in doc.pages)
    page_lo = doc.pages[0].page_index if doc.pages else 0
    page_hi = doc.pages[-1].page_index if doc.pages else 0

    sections: list[str] = []
    current: list[str] = []
    for line in full_text.splitlines():
        if re.match(r"^\s{0,3}#{1,3}\s+\S", line):
            if current:
                sections.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current).strip())
    if not sections:
        sections = [full_text.strip()]

    out: List[ChunkRecord] = []
    for sec_i, body in enumerate(sections, start=1):
        if not body:
            continue
        if len(body) <= max_chars:
            qual = f"sec{sec_i}"
            out.append(
                ChunkRecord(
                    chunk_id=_chunk_id(course, parsed_slug, qual),
                    course=course,
                    source_type="review_section",
                    document_name=document_name,
                    source_path=doc.source_path,
                    parsed_slug=parsed_slug,
                    page_span=[page_lo, page_hi],
                    question_id=str(sec_i),
                    text=body,
                )
            )
            continue
        paras = [p.strip() for p in body.split("\n\n") if p.strip()]
        buf = ""
        pi = 0
        for p in paras:
            if len(buf) + len(p) + 2 <= max_chars:
                buf = f"{buf}\n\n{p}".strip() if buf else p
            else:
                if buf:
                    pi += 1
                    qual = f"sec{sec_i}_part{pi}"
                    out.append(
                        ChunkRecord(
                            chunk_id=_chunk_id(course, parsed_slug, qual),
                            course=course,
                            source_type="review_section",
                            document_name=document_name,
                            source_path=doc.source_path,
                            parsed_slug=parsed_slug,
                            page_span=[page_lo, page_hi],
                            question_id=f"{sec_i}_{pi}",
                            text=buf,
                        )
                    )
                buf = p
        if buf:
            pi += 1
            qual = f"sec{sec_i}_part{pi}"
            out.append(
                ChunkRecord(
                    chunk_id=_chunk_id(course, parsed_slug, qual),
                    course=course,
                    source_type="review_section",
                    document_name=document_name,
                    source_path=doc.source_path,
                    parsed_slug=parsed_slug,
                    page_span=[page_lo, page_hi],
                    question_id=f"{sec_i}_{pi}",
                    text=buf,
                )
            )
    return out


def chunk_parsed_document(doc: ParsedDocument) -> List[ChunkRecord]:
    role = doc.document_role
    if role == "lecture":
        return chunk_lecture(doc)
    if role in ("exam", "solution"):
        return chunk_exam_like(doc)
    if role == "review":
        return chunk_review(doc)
    return chunk_lecture(doc, min_merge_chars=0)
