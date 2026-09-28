from __future__ import annotations

import os
import random
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Session as DbSession
from question_bank.paths import final_bank_dir, topics_config_path
from question_bank.select import (
    SelectedPracticeQuestion,
    select_questions,
    select_questions_by_ids,
)
from question_bank.topics_config import load_topics_config

router = APIRouter()

_MAX_SELECTION = 20


def _normalize_course_id(course_id: str) -> str:
    """Align with ``final_question_bank/<COURSE>/`` (typically uppercase, e.g. CS109)."""
    return course_id.strip().upper()


def _enabled_course_ids() -> list[str]:
    raw = (os.environ.get("QUESTION_BANK_ENABLED_COURSES") or "CS109").strip()
    return [c.strip() for c in raw.split(",") if c.strip()]


class CourseOut(BaseModel):
    id: str
    title: str


class TopicOut(BaseModel):
    id: str
    name: str


class SelectionIn(BaseModel):
    topic_id: str
    count: int = Field(ge=1, le=_MAX_SELECTION)
    seed: int | None = None
    student_id: int | None = None


class SelectionQuestionOut(BaseModel):
    id: str
    text: str
    rubric_items: list[str]
    difficulty: str
    hints: list[str] = Field(default_factory=list)


class SelectionOut(BaseModel):
    questions: list[SelectionQuestionOut]


def _study_plan_from_device_info(device_info: Any) -> dict[str, Any] | None:
    if not isinstance(device_info, dict):
        return None
    study_plan = device_info.get("study_plan")
    return study_plan if isinstance(study_plan, dict) else None


def _student_id_from_study_plan(study_plan: dict[str, Any]) -> int | None:
    raw = study_plan.get("student_id")
    if raw is None:
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _session_student_id(session: DbSession, study_plan: dict[str, Any] | None) -> int | None:
    """Resolve the student for a session from the column or embedded study_plan."""
    if session.student_id is not None:
        try:
            parsed = int(session.student_id)
        except (TypeError, ValueError):
            parsed = None
        if parsed is not None and parsed > 0:
            return parsed
    if study_plan is not None:
        return _student_id_from_study_plan(study_plan)
    return None


def _study_plan_matches(
    study_plan: dict[str, Any],
    *,
    course_id: str,
    topic_id: str | None,
) -> bool:
    plan_course = str(study_plan.get("course") or "").strip()
    if plan_course and _normalize_course_id(plan_course) != course_id:
        return False
    plan_topic = str(study_plan.get("topic_id") or "").strip()
    if topic_id and plan_topic and plan_topic != topic_id:
        return False
    return True


def _seen_question_ids_by_topic(
    db: Session,
    *,
    student_id: int,
    course_id: str,
    topic_id: str | None = None,
) -> dict[str, list[str]]:
    # Include rows where student_id was only stored inside device_info.study_plan.
    sessions = (
        db.query(DbSession)
        .filter(
            or_(
                DbSession.student_id == student_id,
                DbSession.student_id.is_(None),
            )
        )
        .order_by(DbSession.started_at.asc(), DbSession.created_at.asc())
        .all()
    )
    seen_by_topic: dict[str, list[str]] = {}
    seen_keys: set[tuple[str, str]] = set()
    for session in sessions:
        study_plan = _study_plan_from_device_info(session.device_info)
        if not study_plan or not _study_plan_matches(study_plan, course_id=course_id, topic_id=topic_id):
            continue
        if _session_student_id(session, study_plan) != student_id:
            continue
        plan_topic = str(study_plan.get("topic_id") or topic_id or "").strip()
        if not plan_topic:
            continue
        raw_ids = study_plan.get("question_ids")
        if not isinstance(raw_ids, list):
            continue
        for raw_id in raw_ids:
            qid = str(raw_id).strip()
            key = (plan_topic, qid)
            if not qid or key in seen_keys:
                continue
            seen_by_topic.setdefault(plan_topic, []).append(qid)
            seen_keys.add(key)
    return seen_by_topic


def _selection_out(picked: list[SelectedPracticeQuestion]) -> SelectionOut:
    return SelectionOut(
        questions=[
            SelectionQuestionOut(
                id=p.id,
                text=p.text,
                rubric_items=p.rubric_items,
                difficulty=p.difficulty,
                hints=p.hints,
            )
            for p in picked
        ]
    )


@router.get("/courses", response_model=list[CourseOut])
def list_question_bank_courses() -> list[CourseOut]:
    """Courses that have both a topics YAML and a final_question_bank directory."""
    out: list[CourseOut] = []
    for course_id in _enabled_course_ids():
        cfg_path = topics_config_path(course_id)
        bank_root = final_bank_dir(course_id)
        if not cfg_path.is_file() or not bank_root.is_dir():
            continue
        try:
            cfg = load_topics_config(cfg_path)
        except Exception:
            continue
        title = f"{cfg.course} - Question Bank"
        out.append(CourseOut(id=_normalize_course_id(course_id), title=title))
    return out


@router.get("/courses/{course_id}/topics", response_model=list[TopicOut])
def list_topics(course_id: str) -> list[TopicOut]:
    cid = _normalize_course_id(course_id)
    cfg_path = topics_config_path(cid)
    if not cfg_path.is_file():
        raise HTTPException(status_code=404, detail=f"No topics config for course {course_id}")
    try:
        cfg = load_topics_config(cfg_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return [TopicOut(id=t.id, name=t.name) for t in cfg.topics]


@router.post("/courses/{course_id}/selection", response_model=SelectionOut)
def select_practice_questions(
    course_id: str,
    body: SelectionIn,
    db: Session = Depends(get_db),
) -> SelectionOut:
    cid = _normalize_course_id(course_id)
    topic_path = final_bank_dir(cid) / f"{body.topic_id}.json"
    if not topic_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"No question bank for topic {body.topic_id!r} in course {cid}",
        )
    rng = random.Random(body.seed) if body.seed is not None else None
    exclude_ids: set[str] | None = None
    if body.student_id is not None:
        seen_by_topic = _seen_question_ids_by_topic(
            db,
            student_id=body.student_id,
            course_id=cid,
            topic_id=body.topic_id,
        )
        exclude_ids = set(seen_by_topic.get(body.topic_id, []))
    try:
        picked: list[SelectedPracticeQuestion] = select_questions(
            cid, body.topic_id, body.count, rng=rng, exclude_ids=exclude_ids
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _selection_out(picked)


@router.get("/courses/{course_id}/seen", response_model=SelectionOut)
def list_seen_practice_questions(
    course_id: str,
    student_id: int = Query(..., ge=1),
    topic_id: str | None = None,
    db: Session = Depends(get_db),
) -> SelectionOut:
    cid = _normalize_course_id(course_id)
    seen_by_topic = _seen_question_ids_by_topic(
        db,
        student_id=student_id,
        course_id=cid,
        topic_id=topic_id,
    )
    picked: list[SelectedPracticeQuestion] = []
    for seen_topic_id, question_ids in seen_by_topic.items():
        topic_path = final_bank_dir(cid) / f"{seen_topic_id}.json"
        if not topic_path.is_file():
            continue
        picked.extend(select_questions_by_ids(cid, seen_topic_id, question_ids))
    return _selection_out(picked)
