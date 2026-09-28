from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from question_bank import select as select_mod


def _minimal_topic_json(questions: list[dict]) -> dict:
    return {
        "topic_id": "t1",
        "topic_name": "T1",
        "course": "CS109",
        "questions": questions,
    }


def test_select_returns_all_when_count_ge_pool(monkeypatch, tmp_path: Path) -> None:
    qs = [
        {
            "question_id": "a",
            "course": "CS109",
            "topic_id": "t1",
            "question_type": "x",
            "difficulty": "easy",
            "question": "Q1?",
            "expected_answer": "A",
            "source_chunk_ids": [],
            "hints": ["Start with the sample space.", "Identify the event subset.", "Compare the subset to the whole space."],
            "rubric": {"full_credit": ["ok"]},
        },
        {
            "question_id": "b",
            "course": "CS109",
            "topic_id": "t1",
            "question_type": "x",
            "difficulty": "hard",
            "question": "Q2?",
            "expected_answer": "B",
            "source_chunk_ids": [],
            "hints": ["Start with the sample space.", "Identify the event subset.", "Compare the subset to the whole space."],
            "rubric": {"full_credit": ["ok"]},
        },
    ]

    def fake_final_bank_dir(course: str) -> Path:
        assert course == "CS109"
        d = tmp_path / "final_question_bank" / course
        d.mkdir(parents=True)
        (d / "t1.json").write_text(json.dumps(_minimal_topic_json(qs)), encoding="utf-8")
        return d

    monkeypatch.setattr(select_mod, "final_bank_dir", fake_final_bank_dir)
    out = select_mod.select_questions("CS109", "t1", 10, rng=random.Random(0))
    assert len(out) == 2
    ids = {p.id for p in out}
    assert ids == {"a", "b"}
    assert all(len(p.hints) == 3 for p in out)


def test_select_stratifies_when_multiple_buckets(monkeypatch, tmp_path: Path) -> None:
    qs = []
    for i, diff in enumerate(["easy", "easy", "medium", "hard"]):
        qs.append(
            {
                "question_id": f"id_{i}",
                "course": "CS109",
                "topic_id": "t1",
                "question_type": "x",
                "difficulty": diff,
                "question": f"Question {i}?",
                "expected_answer": "x",
                "source_chunk_ids": [],
                "hints": ["Start with the sample space.", "Identify the event subset.", "Compare the subset to the whole space."],
                "rubric": {"full_credit": ["r"]},
            }
        )

    def fake_final_bank_dir(course: str) -> Path:
        d = tmp_path / "final_question_bank" / course
        d.mkdir(parents=True)
        (d / "t1.json").write_text(json.dumps(_minimal_topic_json(qs)), encoding="utf-8")
        return d

    monkeypatch.setattr(select_mod, "final_bank_dir", fake_final_bank_dir)
    rng = random.Random(42)
    out = select_mod.select_questions("CS109", "t1", 3, rng=rng)
    assert len(out) == 3
    diffs = {p.difficulty for p in out}
    # With 3 buckets and count 3, stratification should hit at least 2 distinct difficulties
    assert len(diffs) >= 2


def test_select_normalizes_malformed_latex_in_output(monkeypatch, tmp_path: Path) -> None:
    qs = [
        {
            "question_id": "bad_binom",
            "course": "CS109",
            "topic_id": "t1",
            "question_type": "x",
            "difficulty": "medium",
            "question": "Explain what $\\binom103$ means in this counting problem.",
            "expected_answer": "A",
            "source_chunk_ids": [],
            "hints": ["Start with the sample space.", "Identify the event subset.", "Compare the subset to the whole space."],
            "rubric": {"full_credit": ["r"]},
        },
        {
            "question_id": "bad_delimiter",
            "course": "CS109",
            "topic_id": "t1",
            "question_type": "x",
            "difficulty": "medium",
            "question": r"Use \(P(A \mid B)\) to solve this counting problem.",
            "expected_answer": "A",
            "source_chunk_ids": [],
            "hints": ["Start with the sample space.", "Identify the event subset.", "Compare the subset to the whole space."],
            "rubric": {"full_credit": ["r"]},
        },
        {
            "question_id": "good_1",
            "course": "CS109",
            "topic_id": "t1",
            "question_type": "x",
            "difficulty": "medium",
            "question": "Explain what $\\binom{10}{3}$ means in this counting problem.",
            "expected_answer": "A",
            "source_chunk_ids": [],
            "hints": ["Start with the sample space.", "Identify the event subset.", "Compare the subset to the whole space."],
            "rubric": {"full_credit": ["r"]},
        },
        {
            "question_id": "good_2",
            "course": "CS109",
            "topic_id": "t1",
            "question_type": "x",
            "difficulty": "medium",
            "question": "Describe this counting setup in words before calculating.",
            "expected_answer": "A",
            "source_chunk_ids": [],
            "hints": ["Start with the sample space.", "Identify the event subset.", "Compare the subset to the whole space."],
            "rubric": {"full_credit": ["r"]},
        },
    ]

    def fake_final_bank_dir(course: str) -> Path:
        d = tmp_path / "final_question_bank" / course
        d.mkdir(parents=True)
        (d / "t1.json").write_text(json.dumps(_minimal_topic_json(qs)), encoding="utf-8")
        return d

    monkeypatch.setattr(select_mod, "final_bank_dir", fake_final_bank_dir)
    out = select_mod.select_questions("CS109", "t1", 4, rng=random.Random(0))

    assert len(out) == 4
    by_id = {p.id: p for p in out}
    assert "\\binom{10}{3}" in by_id["bad_binom"].text
    assert r"\(" not in by_id["bad_delimiter"].text
    assert "$" in by_id["bad_delimiter"].text


def test_select_excludes_seen_question_ids(monkeypatch, tmp_path: Path) -> None:
    qs = []
    for qid in ["seen_1", "new_1", "seen_2", "new_2"]:
        qs.append(
            {
                "question_id": qid,
                "course": "CS109",
                "topic_id": "t1",
                "question_type": "x",
                "difficulty": "medium",
                "question": f"Question {qid.replace('_', ' ')}?",
                "expected_answer": "A",
                "source_chunk_ids": [],
                "hints": ["Start with the sample space.", "Identify the event subset.", "Compare the subset to the whole space."],
                "rubric": {"full_credit": ["r"]},
            }
        )

    def fake_final_bank_dir(course: str) -> Path:
        d = tmp_path / "final_question_bank" / course
        d.mkdir(parents=True)
        (d / "t1.json").write_text(json.dumps(_minimal_topic_json(qs)), encoding="utf-8")
        return d

    monkeypatch.setattr(select_mod, "final_bank_dir", fake_final_bank_dir)
    out = select_mod.select_questions(
        "CS109",
        "t1",
        4,
        rng=random.Random(0),
        exclude_ids={"seen_1", "seen_2"},
    )

    assert {p.id for p in out} == {"new_1", "new_2"}


def test_select_returns_empty_when_all_questions_are_excluded(monkeypatch, tmp_path: Path) -> None:
    qs = [
        {
            "question_id": "seen",
            "course": "CS109",
            "topic_id": "t1",
            "question_type": "x",
            "difficulty": "medium",
            "question": "Question seen?",
            "expected_answer": "A",
            "source_chunk_ids": [],
            "hints": ["Start with the sample space.", "Identify the event subset.", "Compare the subset to the whole space."],
            "rubric": {"full_credit": ["r"]},
        }
    ]

    def fake_final_bank_dir(course: str) -> Path:
        d = tmp_path / "final_question_bank" / course
        d.mkdir(parents=True)
        (d / "t1.json").write_text(json.dumps(_minimal_topic_json(qs)), encoding="utf-8")
        return d

    monkeypatch.setattr(select_mod, "final_bank_dir", fake_final_bank_dir)
    out = select_mod.select_questions("CS109", "t1", 1, exclude_ids={"seen"})

    assert out == []
