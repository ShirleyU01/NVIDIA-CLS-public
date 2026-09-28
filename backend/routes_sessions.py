from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session as OrmSession

from .db import get_db
from . import models, schemas


router = APIRouter(prefix="/sessions", tags=["sessions"])


def _generate_session_id() -> str:
    # Human-readable session id; for now, UUID4.
    return f"session-{uuid.uuid4().hex[:8]}"


@router.post("", response_model=schemas.SessionRead)
def create_session(payload: schemas.SessionCreate, db: OrmSession = Depends(get_db)) -> schemas.SessionRead:
    session_id = _generate_session_id()
    now = datetime.utcnow()
    db_session = models.Session(
        id=session_id,
        assessment_id=payload.assessment_id,
        student_id=payload.student_id,
        device_info=payload.device_info,
        status="created",
        evidence_packet_status="pending",
        created_at=now,
        updated_at=now,
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return schemas.SessionRead.from_orm(db_session)


@router.get("/{session_id}", response_model=schemas.SessionDetailRead)
def get_session_detail(session_id: str, db: OrmSession = Depends(get_db)) -> schemas.SessionDetailRead:
    db_session = db.query(models.Session).filter(models.Session.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    db_packet = db.query(models.EvidencePacket).filter(models.EvidencePacket.session_id == session_id).first()
    session_read = schemas.SessionRead.from_orm(db_session)
    evidence_read = None
    if db_packet and db_packet.packet_json is not None:
        evidence_read = schemas.EvidencePacketRead(
            session_id=db_packet.session_id,
            rubric_id=db_packet.rubric_id,
            packet_json=db_packet.packet_json,
        )
    return schemas.SessionDetailRead(session=session_read, evidence_packet=evidence_read)


@router.post("/{session_id}/artifacts", response_model=schemas.SessionRead)
def register_artifacts(
    session_id: str,
    payload: schemas.SessionArtifactUpdate,
    background_tasks: BackgroundTasks,
    db: OrmSession = Depends(get_db),
) -> schemas.SessionRead:
    db_session = db.query(models.Session).filter(models.Session.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")

    artifacts = db_session.artifacts or {}
    if payload.recording_uri:
        artifacts["recording_uri"] = payload.recording_uri
    if payload.final_transcript_uri:
        artifacts["final_transcript_uri"] = payload.final_transcript_uri
    if payload.transcript_uri:
        artifacts["transcript_uri"] = payload.transcript_uri
    if payload.session_dir_uri:
        artifacts["session_dir_uri"] = payload.session_dir_uri
    if payload.extra:
        artifacts.update(payload.extra)

    db_session.artifacts = artifacts
    db_session.status = "evidence_pending"
    db_session.evidence_packet_status = "processing"
    db_session.updated_at = datetime.utcnow()
    db.add(db_session)
    db.commit()
    db.refresh(db_session)

    # Evidence packet generation will be wired here in a follow-up step.
    # background_tasks.add_task(run_evidence_job_for_session, session_id)

    return schemas.SessionRead.from_orm(db_session)

