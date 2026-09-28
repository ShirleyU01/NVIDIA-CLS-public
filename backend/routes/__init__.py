from __future__ import annotations

from fastapi import APIRouter

from . import assessments, question_bank, question_sets, rubrics, sessions, students, study_dashboard

api_router = APIRouter()

api_router.include_router(rubrics.router, prefix="/rubrics", tags=["rubrics"])
api_router.include_router(
    question_sets.router, prefix="/question-sets", tags=["question_sets"]
)
api_router.include_router(assessments.router, prefix="/assessments", tags=["assessments"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(students.router, prefix="/students", tags=["students"])
api_router.include_router(
    question_bank.router, prefix="/question-bank", tags=["question_bank"]
)
api_router.include_router(
    study_dashboard.router, prefix="/study-dashboard", tags=["study_dashboard"]
)

