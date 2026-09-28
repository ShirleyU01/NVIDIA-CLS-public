"""
Tests for the central backend exposing study-mode post-session feedback on
``GET /sessions/:id``.

Backed by an in-memory SQLite database (``StaticPool`` so all connections
share the same database) and the FastAPI ``TestClient``. We seed a minimal
``Assessment`` + ``Session`` row whose ``artifacts`` already contain the
``study_feedback`` / ``study_teacher_summary`` blobs the Jetson would have
POSTed via ``/sessions/{id}/artifacts``.
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
    """Build an isolated in-memory SQLite engine + session factory per test."""
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
    """A TestClient wired to the isolated in-memory DB."""

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


def _seed_session(db_session_factory, *, session_id: str, artifacts: dict) -> None:
    """Insert the minimum row graph needed to GET ``/sessions/:id``."""
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
                started_at=datetime.utcnow(),
                status="created",
                artifacts=artifacts,
            )
        )
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_get_session_surfaces_study_feedback_when_present(client, db_session_factory):
    _seed_session(
        db_session_factory,
        session_id="sess-ok",
        artifacts={
            "study_feedback": {
                "question": "Q?",
                "high_level_takeaways": [
                    "Set up the free-body diagram correctly.",
                    "Improved between capture 1 and capture 2.",
                ],
                "areas_to_improve": ["Units were dropped in capture 1."],
                "next_steps": ["Redo the block problem writing units at every step."],
            },
            "study_teacher_summary": {
                "summary": "Strong.",
                "flags": ["check units"],
                "action_items": ["Re-teach units"],
            },
        },
    )

    resp = client.get("/sessions/sess-ok")
    assert resp.status_code == 200
    body = resp.json()
    feedback = body["study_feedback"]
    assert feedback["question"] == "Q?"
    assert feedback["high_level_takeaways"] == [
        "Set up the free-body diagram correctly.",
        "Improved between capture 1 and capture 2.",
    ]
    assert feedback["areas_to_improve"] == ["Units were dropped in capture 1."]
    assert feedback["next_steps"] == [
        "Redo the block problem writing units at every step."
    ]
    # Legacy keys must not leak through.
    assert "steps" not in feedback
    assert "summary" not in feedback

    assert body["study_teacher_summary"]["summary"] == "Strong."
    assert body["study_teacher_summary"]["flags"] == ["check units"]
    assert body["study_teacher_summary"]["action_items"] == ["Re-teach units"]


# ---------------------------------------------------------------------------
# Negative paths
# ---------------------------------------------------------------------------


def test_missing_keys_yield_null_fields(client, db_session_factory):
    _seed_session(db_session_factory, session_id="sess-empty", artifacts={})
    resp = client.get("/sessions/sess-empty")
    assert resp.status_code == 200
    body = resp.json()
    assert body["study_feedback"] is None
    assert body["study_teacher_summary"] is None


def test_malformed_blobs_yield_null(client, db_session_factory):
    _seed_session(
        db_session_factory,
        session_id="sess-bad",
        artifacts={
            "study_feedback": "not a dict",
            "study_teacher_summary": ["also not a dict"],
        },
    )
    resp = client.get("/sessions/sess-bad")
    assert resp.status_code == 200
    body = resp.json()
    assert body["study_feedback"] is None
    assert body["study_teacher_summary"] is None


def test_non_list_sections_coerce_to_empty_arrays(client, db_session_factory):
    """If a section comes in as the wrong type, the extractor normalizes it
    to an empty list rather than propagating garbage to the frontend.
    """
    _seed_session(
        db_session_factory,
        session_id="sess-mixed",
        artifacts={
            "study_feedback": {
                "question": "Q?",
                "high_level_takeaways": "not a list",
                "areas_to_improve": ["", None, "real area"],
                "next_steps": None,
            },
            "study_teacher_summary": {
                "summary": "s",
                "flags": ["", None, "real flag"],
                "action_items": "not a list",
            },
        },
    )
    resp = client.get("/sessions/sess-mixed")
    assert resp.status_code == 200
    body = resp.json()
    feedback = body["study_feedback"]
    assert feedback["question"] == "Q?"
    assert feedback["high_level_takeaways"] == []
    assert feedback["areas_to_improve"] == ["real area"]
    assert feedback["next_steps"] == []
    assert body["study_teacher_summary"]["flags"] == ["real flag"]
    assert body["study_teacher_summary"]["action_items"] == []


def test_missing_sections_default_to_empty_arrays(client, db_session_factory):
    """A partially-populated study_feedback dict still returns a well-shaped
    object with empty arrays for the missing sections."""
    _seed_session(
        db_session_factory,
        session_id="sess-partial",
        artifacts={
            "study_feedback": {
                "question": "Q?",
                "high_level_takeaways": ["only this section present"],
            }
        },
    )
    body = client.get("/sessions/sess-partial").json()
    feedback = body["study_feedback"]
    assert feedback["high_level_takeaways"] == ["only this section present"]
    assert feedback["areas_to_improve"] == []
    assert feedback["next_steps"] == []
