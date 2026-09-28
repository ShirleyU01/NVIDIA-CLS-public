from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend import schemas
from backend.database import get_db
from backend.models import QuestionSet

router = APIRouter()


@router.post("", response_model=schemas.QuestionSetRead)
def create_question_set(
    payload: schemas.QuestionSetCreate, db: Session = Depends(get_db)
):
    question_set = QuestionSet(
        title=payload.title,
        subject=payload.subject,
        question_set_json=payload.question_set_json,
    )
    db.add(question_set)
    db.commit()
    db.refresh(question_set)
    return question_set


@router.get("/{question_set_id}", response_model=schemas.QuestionSetRead)
def get_question_set(question_set_id: int, db: Session = Depends(get_db)):
    question_set = db.get(QuestionSet, question_set_id)
    if not question_set:
        raise HTTPException(status_code=404, detail="Question set not found")
    return question_set

