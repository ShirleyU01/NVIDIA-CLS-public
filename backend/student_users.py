"""Create lightweight student rows on first sign-in (no pre-registration required)."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import User


def ensure_student_user(db: Session, student_id: int) -> User:
    """
    Return a ``users`` row for this numeric student ID, creating one if needed.

    Study sessions reference ``users.id`` via foreign key; first-time students
    must exist before we insert a session row.
    """
    if student_id <= 0:
        raise ValueError("student_id must be a positive integer")

    existing = db.get(User, student_id)
    if existing is not None:
        return existing

    user = User(
        id=student_id,
        role="student",
        name=f"Student {student_id}",
        email=None,
    )
    nested = db.begin_nested()
    try:
        db.add(user)
        db.flush()
        nested.commit()
    except IntegrityError:
        nested.rollback()
        existing = db.get(User, student_id)
        if existing is None:
            raise
        return existing
    return user
