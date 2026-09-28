from __future__ import annotations

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


def _seed_session(db_session_factory, *, session_id: str) -> None:
    db = db_session_factory()
    try:
        rubric = Rubric(title="r", subject="s", rubric_json={})
        question_set = QuestionSet(title="qs", subject="s", question_set_json={})
        db.add_all([rubric, question_set])
        db.flush()
        assessment = Assessment(
            rubric_id=rubric.id,
            question_set_id=question_set.id,
            title="a",
            status="published",
        )
        db.add(assessment)
        db.flush()
        db.add(
            DbSession(
                id=session_id,
                assessment_id=assessment.id,
                student_id=2101,
                started_at=datetime.utcnow(),
                status="created",
                device_info={
                    "study_plan": {
                        "course": "CS109",
                        "topic_id": "t1",
                        "student_id": 2101,
                        "question_ids": [],
                    }
                },
            )
        )
        db.commit()
    finally:
        db.close()


def test_study_seen_finalize_false_keeps_session_open(
    client: TestClient,
    db_session_factory,
) -> None:
    _seed_session(db_session_factory, session_id="sess-progress")

    resp = client.post(
        "/sessions/sess-progress/study-seen",
        json={
            "student_id": 2101,
            "course": "CS109",
            "topic_id": "t1",
            "question_ids": ["q1"],
            "finalize": False,
        },
    )
    assert resp.status_code == 200

    db = db_session_factory()
    try:
        row = db.get(DbSession, "sess-progress")
        assert row is not None
        assert row.status == "created"
        assert row.ended_at is None
        assert row.device_info["study_plan"]["question_ids"] == ["q1"]
    finally:
        db.close()


def test_study_seen_merges_ids_and_finalizes_session(
    client: TestClient,
    db_session_factory,
) -> None:
    _seed_session(db_session_factory, session_id="sess-progress")

    client.post(
        "/sessions/sess-progress/study-seen",
        json={
            "student_id": 2101,
            "course": "CS109",
            "topic_id": "t1",
            "question_ids": ["q1"],
            "finalize": False,
        },
    )
    resp = client.post(
        "/sessions/sess-progress/study-seen",
        json={
            "student_id": 2101,
            "course": "CS109",
            "topic_id": "t1",
            "question_ids": ["q2"],
            "finalize": True,
        },
    )
    assert resp.status_code == 200

    db = db_session_factory()
    try:
        row = db.get(DbSession, "sess-progress")
        assert row is not None
        assert row.status == "completed"
        assert row.ended_at is not None
        assert row.device_info["study_plan"]["question_ids"] == ["q1", "q2"]
    finally:
        db.close()
