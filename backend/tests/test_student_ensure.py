from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend import main as backend_main  # noqa: E402
from backend.database import Base, get_db  # noqa: E402
from backend.models import Assessment, QuestionSet, Rubric, User  # noqa: E402


@pytest.fixture()
def db_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

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


def _auth_header() -> dict[str, str]:
    token = base64.b64encode(b"teacher:dropouts210").decode()
    return {"Authorization": f"Basic {token}"}


def _seed_assessment(db_session_factory) -> int:
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
        db.commit()
        return assessment.id
    finally:
        db.close()


def test_ensure_creates_new_student(client: TestClient, db_session_factory) -> None:
    resp = client.post("/students/ensure", json={"student_id": 4242})
    assert resp.status_code == 200
    body = resp.json()
    assert body["student_id"] == 4242
    assert body["created"] is True

    db = db_session_factory()
    try:
        user = db.get(User, 4242)
        assert user is not None
        assert user.role == "student"
    finally:
        db.close()


def test_create_session_succeeds_for_first_time_student(
    client: TestClient,
    db_session_factory,
) -> None:
    assessment_id = _seed_assessment(db_session_factory)
    resp = client.post(
        "/sessions",
        json={
            "assessment_id": assessment_id,
            "student_id": 5151,
            "device_info": {
                "study_plan": {
                    "course": "CS109",
                    "topic_id": "t1",
                    "student_id": 5151,
                    "question_ids": ["q1"],
                }
            },
        },
        headers=_auth_header(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["student_id"] == 5151
