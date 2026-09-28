from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from backend import schemas
from backend.database import get_db
from backend.models import (
    Assessment,
    EvidencePacket,
    QuestionSet,
    Rubric,
    Session as DbSession,
)

router = APIRouter()


@router.post("", response_model=schemas.AssessmentRead)
def create_assessment(payload: schemas.AssessmentCreate, db: Session = Depends(get_db)):
    rubric = db.get(Rubric, payload.rubric_id)
    if not rubric:
        raise HTTPException(status_code=400, detail="Invalid rubric_id")

    question_set = db.get(QuestionSet, payload.question_set_id)
    if not question_set:
        raise HTTPException(status_code=400, detail="Invalid question_set_id")

    assessment = Assessment(
        rubric_id=payload.rubric_id,
        question_set_id=payload.question_set_id,
        title=payload.title,
        description=payload.description,
        status="draft",
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment


@router.get("", response_model=List[schemas.AssessmentSummary])
def list_assessments(db: Session = Depends(get_db)):
    # Aggregate total_sessions and unreviewed_sessions per assessment.
    subq = (
        select(
            DbSession.assessment_id,
            func.count(DbSession.id).label("total"),
            func.sum(
                case(
                    (DbSession.status != "reviewed", 1),
                    else_=0,
                )
            ).label("unreviewed"),
        )
        .group_by(DbSession.assessment_id)
        .subquery()
    )
    q = (
        db.query(
            Assessment.id,
            Assessment.title,
            func.coalesce(subq.c.total, 0),
            func.coalesce(subq.c.unreviewed, 0),
        )
        .outerjoin(subq, Assessment.id == subq.c.assessment_id)
        .order_by(Assessment.id)
    )
    items = []
    for aid, title, total, unreviewed in q:
        items.append(
            schemas.AssessmentSummary(
                id=aid,
                title=title,
                total_sessions=int(total or 0),
                unreviewed_sessions=int(unreviewed or 0),
            )
        )
    return items


@router.get("/{assessment_id}", response_model=schemas.AssessmentRead)
def get_assessment(assessment_id: int, db: Session = Depends(get_db)):
    assessment = db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return assessment


@router.get("/{assessment_id}/exam-config")
def get_assessment_exam_config(assessment_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    assessment = db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    question_set = db.get(QuestionSet, assessment.question_set_id)
    if not question_set:
        raise HTTPException(status_code=404, detail="Question set not found")

    return {
        "assessment_id": assessment.id,
        "assessment_title": assessment.title,
        "exam_config": question_set.question_set_json,
    }


@router.get("/{assessment_id}/sessions", response_model=schemas.AssessmentSessionsResponse)
def get_assessment_sessions(assessment_id: int, db: Session = Depends(get_db)):
    assessment = db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    # Basic session summaries
    sessions = (
        db.query(DbSession)
        .filter(DbSession.assessment_id == assessment_id)
        .order_by(DbSession.started_at.desc().nullslast())
        .all()
    )
    session_summaries: List[schemas.SessionSummary] = []
    for s in sessions:
        session_summaries.append(
            schemas.SessionSummary(
                id=s.id,
                assessment_id=s.assessment_id,
                student_id=s.student_id,
                student_name=None,
                date_iso=s.started_at,
                status=s.status,
                score=float(s.score_total) if s.score_total is not None else None,
            )
        )

    # Optional grade buckets based on evidence packets (very simple A/B/C/D bucketing).
    grade_buckets: List[schemas.GradeBucket] = []
    if sessions:
        epackets = (
            db.query(EvidencePacket)
            .join(DbSession, EvidencePacket.session_id == DbSession.id)
            .filter(DbSession.assessment_id == assessment_id)
            .all()
        )
        scores = []
        for p in epackets:
            total = p.packet_json.get("total_score")
            max_score = p.packet_json.get("max_score") or 1
            try:
                ratio = float(total) / float(max_score)
                scores.append(ratio)
            except Exception:
                continue
        if scores:
            def bucket(r: float) -> str:
                if r >= 0.9:
                    return "A"
                if r >= 0.8:
                    return "B"
                if r >= 0.7:
                    return "C"
                return "D"

            from collections import Counter

            counts = Counter(bucket(r) for r in scores)
            for label in ["A", "B", "C", "D"]:
                if counts.get(label):
                    grade_buckets.append(
                        schemas.GradeBucket(label=label, count=counts[label])
                    )

    return schemas.AssessmentSessionsResponse(
        assessment=schemas.AssessmentRead.from_orm(assessment),
        sessions=session_summaries,
        grade_buckets=grade_buckets,
    )

