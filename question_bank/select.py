"""
Select a practice subset from the file-backed final question bank.

Implements difficulty-aware random sampling (see docs/QUESTION-BANK-STUDY-MODE-INTEGRATION.md §0.1).
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from question_bank.export import flatten_rubric
from question_bank.latex_fix import fix_latex_for_katex
from question_bank.latex_validation import latex_issues
from question_bank.paths import final_bank_dir
from question_bank.schemas import CanonicalQuestion


@dataclass(frozen=True)
class SelectedPracticeQuestion:
    """Shape sent to Jetson / student UI."""

    id: str
    text: str
    rubric_items: list[str]
    difficulty: str
    hints: list[str]


def _normalize_difficulty(raw: str) -> str:
    s = (raw or "").strip().lower()
    return s if s else "unspecified"


def load_topic_question_pool(course: str, topic_id: str) -> list[CanonicalQuestion]:
    """Load all canonical questions for one topic from ``<topic_id>.json``."""
    path: Path = final_bank_dir(course) / f"{topic_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"No question bank file at {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    questions_raw = raw.get("questions") if isinstance(raw, dict) else None
    if not isinstance(questions_raw, list):
        return []
    out: list[CanonicalQuestion] = []
    for item in questions_raw:
        if not isinstance(item, dict):
            continue
        try:
            out.append(CanonicalQuestion.model_validate(item))
        except Exception:
            continue
    return out


def _latex_texts(q: CanonicalQuestion) -> list[str]:
    texts = [q.question or ""]
    texts.extend(q.hints)
    texts.extend(flatten_rubric(q.rubric))
    return texts


def canonical_to_selected(q: CanonicalQuestion) -> SelectedPracticeQuestion:
    text = fix_latex_for_katex((q.question or "").strip())
    rubric_items = [fix_latex_for_katex(x) for x in flatten_rubric(q.rubric)]
    return SelectedPracticeQuestion(
        id=q.question_id,
        text=text,
        rubric_items=rubric_items,
        difficulty=_normalize_difficulty(q.difficulty),
        hints=[fix_latex_for_katex(h.strip()) for h in q.hints if h.strip()],
    )


def _has_render_unsafe_latex(q: CanonicalQuestion) -> bool:
    return any(latex_issues(fix_latex_for_katex(text)) for text in _latex_texts(q))


def select_questions(
    course: str,
    topic_id: str,
    count: int,
    *,
    rng: random.Random | None = None,
    exclude_ids: set[str] | None = None,
) -> list[SelectedPracticeQuestion]:
    """
    Return up to ``count`` questions: random without replacement, stratified by
    difficulty when the pool has multiple buckets and N allows it.
    """
    if count < 1:
        raise ValueError("count must be at least 1")
    excluded = {str(qid).strip() for qid in (exclude_ids or set()) if str(qid).strip()}
    # Build the eligible pool before sampling so malformed LaTeX is replaced by
    # another safe question from the same topic whenever one is available.
    pool = [
        canonical_to_selected(q)
        for q in load_topic_question_pool(course, topic_id)
        if not _has_render_unsafe_latex(q) and q.question_id not in excluded
    ]
    pool = [p for p in pool if p.text]
    if not pool:
        return []
    r = rng or random.Random()

    if count >= len(pool):
        r.shuffle(pool)
        return pool

    # Group by difficulty bucket
    buckets: dict[str, list[SelectedPracticeQuestion]] = {}
    for p in pool:
        buckets.setdefault(p.difficulty, []).append(p)
    for b in buckets.values():
        r.shuffle(b)

    bucket_keys = sorted(buckets.keys())
    non_empty = [k for k in bucket_keys if buckets[k]]

    chosen: list[SelectedPracticeQuestion] = []
    used_ids: set[str] = set()

    def pick_from_bucket(key: str) -> SelectedPracticeQuestion | None:
        for cand in buckets[key]:
            if cand.id not in used_ids:
                return cand
        return None

    def pick_any() -> SelectedPracticeQuestion | None:
        rest = [p for p in pool if p.id not in used_ids]
        if not rest:
            return None
        return r.choice(rest)

    # Round-robin one from each non-empty bucket while we need more and have buckets left
    if len(non_empty) > 1 and count >= len(non_empty):
        for key in non_empty:
            if len(chosen) >= count:
                break
            c = pick_from_bucket(key)
            if c:
                chosen.append(c)
                used_ids.add(c.id)

    while len(chosen) < count:
        c = pick_any()
        if c is None:
            break
        chosen.append(c)
        used_ids.add(c.id)

    r.shuffle(chosen)
    return chosen


def select_questions_by_ids(
    course: str,
    topic_id: str,
    question_ids: list[str],
) -> list[SelectedPracticeQuestion]:
    """
    Return questions by ID in the caller's order. Used for reviewing previously
    seen questions without random sampling.
    """
    requested_ids: list[str] = []
    seen: set[str] = set()
    for qid in question_ids:
        clean = str(qid).strip()
        if clean and clean not in seen:
            requested_ids.append(clean)
            seen.add(clean)
    if not requested_ids:
        return []

    by_id = {
        q.question_id: canonical_to_selected(q)
        for q in load_topic_question_pool(course, topic_id)
        if not _has_render_unsafe_latex(q)
    }
    return [by_id[qid] for qid in requested_ids if qid in by_id]
