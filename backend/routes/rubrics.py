from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend import schemas
from backend.database import get_db
from backend.models import Rubric

router = APIRouter()


@router.post("", response_model=schemas.RubricRead)
def create_rubric(payload: schemas.RubricCreate, db: Session = Depends(get_db)):
    rubric = Rubric(
        title=payload.title,
        subject=payload.subject,
        rubric_json=payload.rubric_json,
    )
    db.add(rubric)
    db.commit()
    db.refresh(rubric)
    return rubric


@router.get("/{rubric_id}", response_model=schemas.RubricRead)
def get_rubric(rubric_id: int, db: Session = Depends(get_db)):
    rubric = db.get(Rubric, rubric_id)
    if not rubric:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Rubric not found")
    return rubric

