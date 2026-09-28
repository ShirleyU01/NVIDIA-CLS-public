from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User
from backend.student_users import ensure_student_user

router = APIRouter()


class StudentEnsureIn(BaseModel):
    student_id: int = Field(ge=1, description="Numeric student ID entered at sign-in")


class StudentEnsureOut(BaseModel):
    student_id: int
    status: str = "ok"
    created: bool


@router.post("/ensure", response_model=StudentEnsureOut)
def ensure_student(
    body: StudentEnsureIn,
    db: Session = Depends(get_db),
) -> StudentEnsureOut:
    """
    Register a student on first sign-in.

    No password and no pre-created roster — any positive numeric ID is accepted.
    """
    existed = db.get(User, body.student_id) is not None
    user = ensure_student_user(db, body.student_id)
    db.commit()
    return StudentEnsureOut(
        student_id=user.id,
        status="ok",
        created=not existed,
    )
