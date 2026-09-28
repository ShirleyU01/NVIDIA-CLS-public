from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Header
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend import schemas
from backend.database import get_db
from backend.evidence_jobs import run_evidence_job
from backend.models import Assessment, EvidencePacket, Session as DbSession, SessionReview
from backend.student_users import ensure_student_user

router = APIRouter()

_TEACHER_USERNAME = "teacher"
_TEACHER_PASSWORD = "dropouts210"


def _unauthorized_basic() -> HTTPException:
    # Browser-friendly prompt for Basic Auth.
    return HTTPException(
        status_code=401,
        detail="Teacher authentication required",
        headers={"WWW-Authenticate": 'Basic realm="teacher"'},
    )


def require_teacher_basic_auth(authorization: str | None = Header(default=None)) -> None:
    """
    Minimal Basic Auth gate for endpoints that create/start sessions.

    This is intentionally lightweight (demo / classroom setups). Do not use
    as-is for production; replace with proper auth + TLS + secrets management.
    """
    if not authorization or not authorization.lower().startswith("basic "):
        raise _unauthorized_basic()
    token = authorization.split(" ", 1)[1].strip()
    try:
        decoded = base64.b64decode(token).decode("utf-8")
    except Exception:
        raise _unauthorized_basic()
    if ":" not in decoded:
        raise _unauthorized_basic()
    username, password = decoded.split(":", 1)
    if username != _TEACHER_USERNAME or password != _TEACHER_PASSWORD:
        raise _unauthorized_basic()


def _load_question_reviews(artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    session_dir_uri = artifacts.get("session_dir_uri")
    if not isinstance(session_dir_uri, str) or not session_dir_uri:
        return []
    transcript_path = Path(session_dir_uri) / "transcript.json"
    if not transcript_path.exists():
        return []

    try:
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    question_reviews: list[dict[str, Any]] = []
    for idx, q in enumerate(transcript.get("questions", []), start=1):
        responses = []
        for resp in q.get("responses", []):
            text = str(resp.get("text", "")).strip()
            if text:
                responses.append(text)
        for follow_up in q.get("follow_ups", []):
            text = str(follow_up.get("response_text", "")).strip()
            if text:
                responses.append(text)
        answer_text = " ".join(responses).strip()
        question_reviews.append(
            {
                "index": idx,
                "question": q.get("question", ""),
                "answer": answer_text,
                "rubric_items": q.get("rubric_items", []),
            }
        )
    return question_reviews


# ---------------------------------------------------------------------------
# Study-mode feedback extraction
#
# The Jetson "/end" endpoint POSTs ``study_feedback`` and
# ``study_teacher_summary`` blobs into ``Session.artifacts``. The helpers
# below validate the on-disk shape and surface them as typed dicts on
# ``GET /sessions/:id``. Both return ``None`` (not a partial dict) whenever
# anything looks malformed so the frontend can rely on a simple
# "is it there or not" check.
# ---------------------------------------------------------------------------

def _coerce_str(value: Any) -> str:
    """Force ``value`` to a stripped string; non-strings become ``""``."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _coerce_str_list(value: Any) -> list[str]:
    """Coerce a JSON value to a list of non-empty strings."""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for entry in value:
        text = _coerce_str(entry)
        if text:
            out.append(text)
    return out


def _extract_study_student_feedback(artifacts: dict[str, Any]) -> dict[str, Any] | None:
    """
    Pull a well-shaped ``study_feedback`` dict out of ``Session.artifacts``.

    Returns ``None`` for anything that isn't a dict; otherwise returns a dict
    with ``question`` plus the three standardized narrative sections
    (``high_level_takeaways`` / ``areas_to_improve`` / ``next_steps``).
    Missing or malformed sections are silently coerced to empty arrays so the
    frontend only has to check "is the blob there or not".
    """
    raw = artifacts.get("study_feedback") if isinstance(artifacts, dict) else None
    if not isinstance(raw, dict):
        return None

    return {
        "question": _coerce_str(raw.get("question")),
        "high_level_takeaways": _coerce_str_list(raw.get("high_level_takeaways")),
        "areas_to_improve": _coerce_str_list(raw.get("areas_to_improve")),
        "next_steps": _coerce_str_list(raw.get("next_steps")),
    }


def _extract_study_teacher_summary(artifacts: dict[str, Any]) -> dict[str, Any] | None:
    """
    Pull a well-shaped ``study_teacher_summary`` dict out of ``Session.artifacts``.
    """
    raw = artifacts.get("study_teacher_summary") if isinstance(artifacts, dict) else None
    if not isinstance(raw, dict):
        return None
    return {
        "summary": _coerce_str(raw.get("summary")),
        "flags": _coerce_str_list(raw.get("flags")),
        "action_items": _coerce_str_list(raw.get("action_items")),
    }


def _load_session_screenshots(artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    """Load screenshot events from session final_transcript.json for display in UI."""
    session_dir_uri = artifacts.get("session_dir_uri")
    if not isinstance(session_dir_uri, str) or not session_dir_uri:
        return []
    final_path = Path(session_dir_uri) / "final_transcript.json"
    if not final_path.exists():
        return []

    try:
        data = json.loads(final_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    events = data.get("events", [])
    result: list[dict[str, Any]] = []
    current_q = None
    for ev in events:
        if ev.get("type") == "question" and not ev.get("follow_up", False):
            current_q = ev.get("question_number")
        elif ev.get("type") == "screenshot" and current_q is not None:
            result.append({
                "question_number": current_q,
                "t": ev.get("t", 0.0),
                "path": ev.get("path", ""),
                "trigger_word": ev.get("trigger_word", ""),
            })
    return result


@router.post("", response_model=schemas.SessionSummary)
def create_session(
    payload: schemas.SessionCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_teacher_basic_auth),
):
    assessment = db.get(Assessment, payload.assessment_id)
    if not assessment:
        raise HTTPException(status_code=400, detail="Invalid assessment_id")
    # For MVP, let caller provide a string session id (e.g. from Jetson),
    # but if not provided, generate a simple timestamp-based id.
    # Here we expect Jetson to supply the id; central-only clients can
    # treat this endpoint as ID generator in a future revision.
    # Use a UUID-based id so concurrent study runs created in the same second
    # do not collide on the sessions.id primary key.
    session_id = f"sess-{uuid4().hex}"
    student_id = payload.student_id
    device_info = dict(payload.device_info or {})
    study_plan = device_info.get("study_plan")
    if student_id is None and isinstance(study_plan, dict):
        raw_plan_student = study_plan.get("student_id")
        if raw_plan_student is not None:
            try:
                parsed = int(raw_plan_student)
                if parsed > 0:
                    student_id = parsed
            except (TypeError, ValueError):
                pass
    if student_id is not None and student_id > 0:
        ensure_student_user(db, student_id)
    s = DbSession(
        id=session_id,
        assessment_id=payload.assessment_id,
        student_id=student_id,
        started_at=datetime.utcnow(),
        device_info=device_info,
        status="created",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return schemas.SessionSummary(
        id=s.id,
        assessment_id=s.assessment_id,
        student_id=s.student_id,
        student_name=None,
        date_iso=s.started_at,
        status=s.status,
        score=None,
    )


@router.post("/{session_id}/study-seen")
def record_study_seen(
    session_id: str,
    payload: schemas.StudySeenRecord,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """
    Record question-bank IDs the student has completed in this study session.

    When ``finalize`` is false, only merges ``question_ids`` into the session's
    study plan (for mid-session progress). When true, also marks the session ended.
    """
    s = db.get(DbSession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    device_info = dict(s.device_info or {})
    study_plan = dict(device_info.get("study_plan") or {})

    if payload.student_id > 0:
        ensure_student_user(db, payload.student_id)
        s.student_id = payload.student_id
        study_plan["student_id"] = payload.student_id

    if payload.course:
        study_plan["course"] = payload.course.strip().upper()
    if payload.topic_id:
        study_plan["topic_id"] = payload.topic_id.strip()

    merged_ids: list[str] = []
    seen_id_keys: set[str] = set()
    for raw in list(study_plan.get("question_ids") or []) + list(payload.question_ids or []):
        qid = str(raw).strip()
        if qid and qid not in seen_id_keys:
            merged_ids.append(qid)
            seen_id_keys.add(qid)
    if merged_ids:
        study_plan["question_ids"] = merged_ids

    if study_plan:
        device_info["study_plan"] = study_plan
        s.device_info = device_info

    if payload.finalize:
        if s.ended_at is None:
            s.ended_at = datetime.utcnow()
        if s.status == "created":
            s.status = "completed"

    db.commit()
    return {"status": "ok"}


@router.get("/study-survey-status", response_model=schemas.StudySurveyStatusRead)
def get_study_survey_status(
    student_id: int,
    db: Session = Depends(get_db),
) -> schemas.StudySurveyStatusRead:
    """Return whether this student has completed the Study Mode exit survey."""
    sessions = db.query(DbSession).filter(DbSession.student_id == student_id).all()
    completed = any(
        isinstance(s.artifacts, dict) and s.artifacts.get("study_survey_completed") is True
        for s in sessions
    )
    return schemas.StudySurveyStatusRead(student_id=student_id, completed=completed)


@router.post(
    "/{session_id}/study-survey-completed",
    response_model=schemas.StudySurveyStatusRead,
)
def mark_study_survey_completed(
    session_id: str,
    payload: schemas.StudySurveyCompletionUpdate = Body(default_factory=schemas.StudySurveyCompletionUpdate),
    db: Session = Depends(get_db),
) -> schemas.StudySurveyStatusRead:
    """Mark a session's student as having completed the Study Mode survey."""
    s = db.get(DbSession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if s.student_id is None:
        raise HTTPException(
            status_code=400,
            detail="Session has no student_id; cannot mark study survey completed",
        )

    artifacts = dict(s.artifacts or {})
    artifacts["study_survey_completed"] = True
    artifacts["study_survey_completed_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    if payload.skipped:
        artifacts["study_survey_skipped"] = True
        artifacts["study_survey_skipped_at"] = artifacts["study_survey_completed_at"]
    s.artifacts = artifacts
    db.commit()
    return schemas.StudySurveyStatusRead(student_id=s.student_id, completed=True)


@router.post("/{session_id}", response_model=schemas.SessionSummary)
def create_or_get_session_with_id(
    session_id: str,
    payload: dict[str, Any] | None = Body(default=None),
    db: Session = Depends(get_db),
    _: None = Depends(require_teacher_basic_auth),
):
    """
    Compatibility endpoint for clients that POST to /sessions/{session_id}.
    If the session already exists, return it; otherwise create it.
    """
    existing = db.get(DbSession, session_id)
    if existing:
        return schemas.SessionSummary(
            id=existing.id,
            assessment_id=existing.assessment_id,
            student_id=existing.student_id,
            student_name=None,
            date_iso=existing.started_at,
            status=existing.status,
            score=float(existing.score_total) if existing.score_total is not None else None,
        )

    payload = payload or {}
    assessment_id = payload.get("assessment_id")
    if assessment_id is None:
        latest_assessment = db.query(Assessment).order_by(Assessment.id.desc()).first()
        if not latest_assessment:
            raise HTTPException(
                status_code=400,
                detail="assessment_id is required when no assessments exist",
            )
        assessment_id = latest_assessment.id

    assessment = db.get(Assessment, int(assessment_id))
    if not assessment:
        raise HTTPException(status_code=400, detail="Invalid assessment_id")

    student_id_raw = payload.get("student_id")
    student_id = int(student_id_raw) if student_id_raw is not None else None
    if student_id is not None and student_id > 0:
        ensure_student_user(db, student_id)
    device_info = payload.get("device_info") or {}
    s = DbSession(
        id=session_id,
        assessment_id=assessment.id,
        student_id=student_id,
        started_at=datetime.utcnow(),
        device_info=device_info,
        status="created",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return schemas.SessionSummary(
        id=s.id,
        assessment_id=s.assessment_id,
        student_id=s.student_id,
        student_name=None,
        date_iso=s.started_at,
        status=s.status,
        score=None,
    )


@router.post("/{session_id}/artifacts")
def update_session_artifacts(
    session_id: str,
    payload: schemas.SessionArtifactsUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    s = db.get(DbSession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    s.artifacts = payload.artifacts
    s.status = "evidence_pending"
    s.evidence_packet_status = "processing"
    s.ended_at = s.ended_at or datetime.utcnow()
    db.commit()
    # Enqueue evidence job
    background_tasks.add_task(run_evidence_job, session_id)
    return {"status": "ok"}


@router.post("/evidence/retry-pending")
def retry_pending_evidence(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Admin/maintenance endpoint: enqueue evidence jobs for all sessions that
    are not yet ready (pending, processing, or previously failed).
    """
    pending_statuses = {"pending", "processing", "failed", "evidence_pending", "evidence_failed"}
    sessions = (
        db.query(DbSession)
        .filter(DbSession.evidence_packet_status.in_(pending_statuses))
        .all()
    )
    for s in sessions:
        background_tasks.add_task(run_evidence_job, s.id)
    return {"enqueued": len(sessions)}


@router.get("/{session_id}", response_model=schemas.SessionDetail)
def get_session_detail(session_id: str, db: Session = Depends(get_db)):
    s = db.get(DbSession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    summary = schemas.SessionSummary(
        id=s.id,
        assessment_id=s.assessment_id,
        student_id=s.student_id,
        student_name=None,
        date_iso=s.started_at,
        status=s.status,
        score=float(s.score_total) if s.score_total is not None else None,
    )

    ep = (
        db.query(EvidencePacket)
        .filter(EvidencePacket.session_id == session_id)
        .one_or_none()
    )
    evidence = (
        schemas.EvidencePacketRead(
            session_id=session_id,
            rubric_id=ep.rubric_id,
            packet_json=ep.packet_json,
        )
        if ep
        else None
    )

    review = (
        db.query(SessionReview)
        .filter(SessionReview.session_id == session_id)
        .order_by(SessionReview.created_at.desc())
        .first()
    )
    review_dict = (
        {
            "final_scores": review.final_scores,
            "comments": review.comments,
            "flags": review.flags,
        }
        if review
        else None
    )

    artifacts = s.artifacts or {}
    return schemas.SessionDetail(
        session=summary,
        evidence_packet=evidence,
        artifacts=artifacts,
        review=review_dict,
        question_reviews=_load_question_reviews(artifacts),
        session_screenshots=_load_session_screenshots(artifacts),
        study_feedback=_extract_study_student_feedback(artifacts),
        study_teacher_summary=_extract_study_teacher_summary(artifacts),
    )


@router.get("/{session_id}/artifacts/files/{file_path:path}")
def get_session_artifact_file(session_id: str, file_path: str, db: Session = Depends(get_db)):
    """
    Serve a file from the session artifacts directory (e.g. images/deixis_xxx.jpg).
    Used so the teacher UI can display screenshots from the evidence packet / session.
    """
    if ".." in file_path or file_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid file path")
    s = db.get(DbSession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    artifacts = s.artifacts or {}
    session_dir_uri = artifacts.get("session_dir_uri")
    if not isinstance(session_dir_uri, str) or not session_dir_uri:
        raise HTTPException(status_code=404, detail="Session artifacts directory not available")
    full_path = Path(session_dir_uri) / file_path
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = "image/jpeg" if file_path.lower().endswith((".jpg", ".jpeg")) else "application/octet-stream"
    return FileResponse(str(full_path), media_type=media_type)


@router.post("/{session_id}/review")
def create_session_review(
    session_id: str, payload: schemas.SessionReviewCreate, db: Session = Depends(get_db)
):
    s = db.get(DbSession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    review = SessionReview(
        session_id=session_id,
        final_scores=payload.final_scores,
        comments=payload.comments,
        flags=payload.flags,
    )
    s.status = "reviewed"
    db.add(review)
    db.commit()
    return {"status": "ok"}

