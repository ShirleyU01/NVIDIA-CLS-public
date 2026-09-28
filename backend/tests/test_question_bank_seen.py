from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend import main as backend_main  # noqa: E402
from backend.database import Base, get_db  # noqa: E402
from backend.models import Assessment, QuestionSet, Rubric, Session as DbSession  # noqa: E402
from backend.routes import question_bank as question_bank_route  # noqa: E402
from question_bank import select as select_mod  # noqa: E402


@pytest.fixture()
def db_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield SessionLocal
    engine.dispose()


@pytest.fixture()
def client(db_session_factory) -> TestClient:
    def override_get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    backend_main.app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(backend_main.app)
    finally:
        backend_main.app.dependency_overrides.pop(get_db, None)


def _topic_payload(questions: list[dict]) -> dict:
    return {
        "topic_id": "t1",
        "topic_name": "T1",
        "course": "CS109",
        "questions": questions,
    }


def _question(qid: str) -> dict:
    return {
        "question_id": qid,
        "course": "CS109",
        "topic_id": "t1",
        "question_type": "conceptual",
        "difficulty": "medium",
        "question": f"Question {qid}?",
        "expected_answer": "A",
        "source_chunk_ids": [],
        "hints": ["Start with the sample space.", "Identify the event subset.", "Compare the subset to the whole space."],
        "rubric": {"full_credit": [f"Rubric {qid}"]},
    }


@pytest.fixture()
def question_bank_files(monkeypatch, tmp_path: Path) -> Path:
    root = tmp_path / "final_question_bank" / "CS109"
    root.mkdir(parents=True)
    (root / "t1.json").write_text(
        json.dumps(_topic_payload([_question("seen"), _question("new"), _question("other")])),
        encoding="utf-8",
    )

    def fake_final_bank_dir(course: str) -> Path:
        return tmp_path / "final_question_bank" / course

    monkeypatch.setattr(question_bank_route, "final_bank_dir", fake_final_bank_dir)
    monkeypatch.setattr(select_mod, "final_bank_dir", fake_final_bank_dir)
    return root


def _seed_session(
    db_session_factory,
    *,
    session_id: str,
    student_id: int,
    study_plan: dict,
) -> None:
    db = db_session_factory()
    try:
        rubric = Rubric(title=f"r-{session_id}", subject="s", rubric_json={})
        question_set = QuestionSet(title=f"qs-{session_id}", subject="s", question_set_json={})
        db.add_all([rubric, question_set])
        db.flush()
        assessment = Assessment(
            rubric_id=rubric.id,
            question_set_id=question_set.id,
            title=f"a-{session_id}",
            status="published",
        )
        db.add(assessment)
        db.flush()
        db.add(
            DbSession(
                id=session_id,
                assessment_id=assessment.id,
                student_id=student_id,
                started_at=datetime.utcnow(),
                status="created",
                device_info={"study_plan": study_plan},
            )
        )
        db.commit()
    finally:
        db.close()


def test_selection_excludes_questions_seen_by_student(
    client: TestClient,
    db_session_factory,
    question_bank_files: Path,
) -> None:
    _seed_session(
        db_session_factory,
        session_id="sess-seen",
        student_id=2101,
        study_plan={"course": "CS109", "topic_id": "t1", "question_ids": ["seen"]},
    )

    resp = client.post(
        "/question-bank/courses/CS109/selection",
        json={"topic_id": "t1", "count": 3, "student_id": 2101},
    )

    assert resp.status_code == 200
    assert {q["id"] for q in resp.json()["questions"]} == {"new", "other"}


def test_seen_endpoint_returns_seen_questions_for_review(
    client: TestClient,
    db_session_factory,
    question_bank_files: Path,
) -> None:
    _seed_session(
        db_session_factory,
        session_id="sess-seen",
        student_id=2101,
        study_plan={"course": "CS109", "topic_id": "t1", "question_ids": ["seen", "new"]},
    )

    resp = client.get(
        "/question-bank/courses/CS109/seen",
        params={"student_id": 2101, "topic_id": "t1"},
    )

    assert resp.status_code == 200
    assert [q["id"] for q in resp.json()["questions"]] == ["seen", "new"]
    assert resp.json()["questions"][0]["text"] == "Question seen?"


def test_seen_lookup_uses_student_id_embedded_in_study_plan(
    client: TestClient,
    db_session_factory,
    question_bank_files: Path,
) -> None:
    db = db_session_factory()
    try:
        rubric = Rubric(title="r-plan-only", subject="s", rubric_json={})
        question_set = QuestionSet(title="qs-plan-only", subject="s", question_set_json={})
        db.add_all([rubric, question_set])
        db.flush()
        assessment = Assessment(
            rubric_id=rubric.id,
            question_set_id=question_set.id,
            title="a-plan-only",
            status="published",
        )
        db.add(assessment)
        db.flush()
        db.add(
            DbSession(
                id="sess-plan-only",
                assessment_id=assessment.id,
                student_id=None,
                started_at=datetime.utcnow(),
                status="created",
                device_info={
                    "study_plan": {
                        "course": "CS109",
                        "topic_id": "t1",
                        "student_id": 2101,
                        "question_ids": ["seen"],
                    }
                },
            )
        )
        db.commit()
    finally:
        db.close()

    resp = client.get(
        "/question-bank/courses/CS109/seen",
        params={"student_id": 2101, "topic_id": "t1"},
    )

    assert resp.status_code == 200
    assert [q["id"] for q in resp.json()["questions"]] == ["seen"]


def test_seen_lookup_ignores_other_students_and_topics(
    client: TestClient,
    db_session_factory,
    question_bank_files: Path,
) -> None:
    _seed_session(
        db_session_factory,
        session_id="sess-other-student",
        student_id=2102,
        study_plan={"course": "CS109", "topic_id": "t1", "question_ids": ["seen"]},
    )
    _seed_session(
        db_session_factory,
        session_id="sess-other-topic",
        student_id=2101,
        study_plan={"course": "CS109", "topic_id": "t2", "question_ids": ["other"]},
    )

    resp = client.get(
        "/question-bank/courses/CS109/seen",
        params={"student_id": 2101, "topic_id": "t1"},
    )

    assert resp.status_code == 200
    assert resp.json()["questions"] == []
