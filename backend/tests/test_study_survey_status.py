"""Tests for central Study Mode survey completion status.

The exit survey itself is written by the Jetson, but the central backend owns
the durable per-student marker used by the web UI to skip repeat surveys.
"""

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
from backend.models import (  # noqa: E402
    Assessment,
    QuestionSet,
    Rubric,
    Session as DbSession,
)


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


def _seed_session(
    db_session_factory,
    *,
    session_id: str,
    student_id: int | None,
    artifacts: dict | None = None,
) -> None:
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
                student_id=student_id,
                started_at=datetime.utcnow(),
                status="created",
                artifacts=artifacts or {},
            )
        )
        db.commit()
    finally:
        db.close()


def test_survey_status_false_when_student_has_no_sessions(client: TestClient) -> None:
    resp = client.get("/sessions/study-survey-status", params={"student_id": 2101})

    assert resp.status_code == 200
    assert resp.json() == {"student_id": 2101, "completed": False}


def test_survey_status_false_without_completion_marker(
    client: TestClient, db_session_factory
) -> None:
    _seed_session(
        db_session_factory,
        session_id="sess-no-marker",
        student_id=2101,
        artifacts={"study_feedback": {"question": "Q?"}},
    )

    resp = client.get("/sessions/study-survey-status", params={"student_id": 2101})

    assert resp.status_code == 200
    assert resp.json() == {"student_id": 2101, "completed": False}


def test_survey_status_true_when_any_student_session_has_marker(
    client: TestClient, db_session_factory
) -> None:
    _seed_session(
        db_session_factory,
        session_id="sess-complete",
        student_id=2101,
        artifacts={"study_survey_completed": True},
    )
    _seed_session(
        db_session_factory,
        session_id="sess-other-student",
        student_id=2102,
        artifacts={},
    )

    resp = client.get("/sessions/study-survey-status", params={"student_id": 2101})

    assert resp.status_code == 200
    assert resp.json() == {"student_id": 2101, "completed": True}


def test_mark_survey_completed_merges_artifact_marker(
    client: TestClient, db_session_factory
) -> None:
    _seed_session(
        db_session_factory,
        session_id="sess-mark",
        student_id=2101,
        artifacts={"study_feedback": {"question": "Q?"}},
    )

    resp = client.post("/sessions/sess-mark/study-survey-completed")

    assert resp.status_code == 200
    assert resp.json()["student_id"] == 2101
    assert resp.json()["completed"] is True

    db = db_session_factory()
    try:
        row = db.get(DbSession, "sess-mark")
        assert row is not None
        assert row.artifacts["study_feedback"] == {"question": "Q?"}
        assert row.artifacts["study_survey_completed"] is True
        assert isinstance(row.artifacts["study_survey_completed_at"], str)
    finally:
        db.close()


def test_mark_survey_completed_can_record_skipped_marker(
    client: TestClient, db_session_factory
) -> None:
    _seed_session(
        db_session_factory,
        session_id="sess-skip",
        student_id=2101,
        artifacts={"study_feedback": {"question": "Q?"}},
    )

    resp = client.post("/sessions/sess-skip/study-survey-completed", json={"skipped": True})

    assert resp.status_code == 200
    assert resp.json() == {"student_id": 2101, "completed": True}

    db = db_session_factory()
    try:
        row = db.get(DbSession, "sess-skip")
        assert row is not None
        assert row.artifacts["study_feedback"] == {"question": "Q?"}
        assert row.artifacts["study_survey_completed"] is True
        assert row.artifacts["study_survey_skipped"] is True
        assert isinstance(row.artifacts["study_survey_completed_at"], str)
        assert row.artifacts["study_survey_skipped_at"] == row.artifacts["study_survey_completed_at"]
    finally:
        db.close()


def test_mark_survey_completed_rejects_session_without_student_id(
    client: TestClient, db_session_factory
) -> None:
    _seed_session(
        db_session_factory,
        session_id="sess-anon",
        student_id=None,
        artifacts={},
    )

    resp = client.post("/sessions/sess-anon/study-survey-completed")

    assert resp.status_code == 400
    assert "student_id" in resp.json()["detail"]
