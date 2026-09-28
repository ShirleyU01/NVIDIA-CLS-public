"""
Aggregate per-capture artifacts into a single ordered list of capture records.

During a study run the Jetson writes one image per capture (``paper_<ts>.jpg``)
into ``jetson_runtime/sessions/<session_id>/paper/`` plus a ``paper_feedback.json``
and ``paper_feedback.md`` that hold the *most recent* grade.

If the writer is later upgraded to suffix per-capture feedback files
(``paper_<ts>.json`` / ``paper_<ts>.md``) this module will pick those up
automatically and attach them to the matching capture; until then, the
"latest" feedback files are attached to the last capture in chronological
order so the LLM at least sees one grounded grade.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class CaptureRecord:
    """One capture (image + best-available LLM grade) within a study session."""

    index: int  # 1-based capture order (oldest = 1) within this question folder or flat session
    image_filename: str  # e.g. "paper_1733000000.jpg"
    feedback_json: Dict[str, Any] = field(default_factory=dict)  # parsed grade JSON
    feedback_md: str = ""  # human-readable grade markdown
    question_index: int = 0  # 0-based; which practice question (multi-question study mode)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_read_json(path: Path) -> Dict[str, Any]:
    """Read ``path`` as a JSON object; return ``{}`` on any error."""
    if not path.exists() or not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _safe_read_text(path: Path) -> str:
    """Read ``path`` as text; return ``""`` on any error."""
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _list_capture_images(session_dir: Path) -> List[Path]:
    """
    Return ``paper_*.jpg`` files in chronological (mtime) order.

    Falls back to filename order if mtimes happen to tie.
    """
    if not session_dir.exists() or not session_dir.is_dir():
        return []
    images = [p for p in session_dir.glob("paper_*.jpg") if p.is_file()]
    images.sort(key=lambda p: (p.stat().st_mtime, p.name))
    return images


def _per_capture_paths(image_path: Path) -> tuple[Path, Path]:
    """
    Map ``paper_<ts>.jpg`` to its sibling ``paper_<ts>.json`` and
    ``paper_<ts>.md`` (which may or may not exist on disk).
    """
    stem = image_path.stem  # "paper_1733000000"
    return (
        image_path.with_name(f"{stem}.json"),
        image_path.with_name(f"{stem}.md"),
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _aggregate_flat_paper_dir(session_dir: Path, *, question_index: int = 0) -> List[CaptureRecord]:
    """Aggregate images directly under ``session_dir`` (legacy flat layout)."""
    images = _list_capture_images(session_dir)
    if not images:
        return []

    records: List[CaptureRecord] = []
    for idx, image_path in enumerate(images, start=1):
        per_json_path, per_md_path = _per_capture_paths(image_path)
        records.append(
            CaptureRecord(
                index=idx,
                image_filename=image_path.name,
                feedback_json=_safe_read_json(per_json_path),
                feedback_md=_safe_read_text(per_md_path),
                question_index=question_index,
            )
        )

    # Backwards-compat: today's writer overwrites a single shared
    # paper_feedback.json/md per session. Attach those to the last capture
    # only if that capture didn't already get a per-capture file picked up.
    shared_json = session_dir / "paper_feedback.json"
    shared_md = session_dir / "paper_feedback.md"
    last = records[-1]
    if not last.feedback_json and shared_json.exists():
        last.feedback_json = _safe_read_json(shared_json)
    if not last.feedback_md and shared_md.exists():
        last.feedback_md = _safe_read_text(shared_md)

    return records


def aggregate_study_session(session_dir: Path) -> List[CaptureRecord]:
    """
    Walk a study session's ``paper/`` directory and build one
    :class:`CaptureRecord` per image, ordered oldest-to-newest.

    **Multi-question layout:** subdirectories ``q0``, ``q1``, … each hold
    captures for that question index. **Legacy layout:** images live directly
    under ``paper/`` (question_index 0).

    Each record's ``feedback_json`` / ``feedback_md`` is populated from
    per-capture files when present; if those don't exist (today's writer
    behavior) the shared ``paper_feedback.json`` / ``paper_feedback.md`` are
    attached to the last capture in that folder. Returns ``[]`` for empty /
    missing dirs.
    """
    if not session_dir.exists() or not session_dir.is_dir():
        return []

    q_subdirs = sorted(
        (
            p
            for p in session_dir.iterdir()
            if p.is_dir() and p.name.startswith("q") and len(p.name) > 1 and p.name[1:].isdigit()
        ),
        key=lambda p: int(p.name[1:]),
    )
    if q_subdirs:
        all_records: List[CaptureRecord] = []
        global_idx = 0
        for qdir in q_subdirs:
            qidx = int(qdir.name[1:])
            chunk = _aggregate_flat_paper_dir(qdir, question_index=qidx)
            for rec in chunk:
                global_idx += 1
                all_records.append(
                    CaptureRecord(
                        index=global_idx,
                        image_filename=f"{qdir.name}/{rec.image_filename}",
                        feedback_json=rec.feedback_json,
                        feedback_md=rec.feedback_md,
                        question_index=qidx,
                    )
                )
        return all_records

    return _aggregate_flat_paper_dir(session_dir, question_index=0)
