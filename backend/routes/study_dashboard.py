from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from fastapi import APIRouter

from backend import schemas
from backend.config import settings

router = APIRouter()

_JETSON_RUNTIME = Path(__file__).resolve().parents[2] / "jetson_runtime"
if str(_JETSON_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_JETSON_RUNTIME))

from study_guide import metrics_log  # noqa: E402
from study_guide.metrics_summary import build_metrics_summary  # noqa: E402


def _metrics_root() -> Path:
    """Metrics live next to the configured Jetson sessions root."""
    return settings.JETSON_SESSIONS_ROOT.parent / "metrics"


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _int(value: Any, default: int = 0) -> int:
    n = _num(value)
    return int(n) if n is not None else default


def _avg(values: Iterable[float | int | None]) -> float | None:
    xs = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not xs:
        return None
    return round(sum(xs) / len(xs), 2)


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def _percent_rate(value: Any) -> float | None:
    n = _num(value)
    if n is None:
        return None
    return round(n * 100, 2) if 0 <= n <= 1 else round(n, 2)


def _avg_time_working_ms(summary: dict[str, Any]) -> float | None:
    per_question = summary.get("per_question")
    if not isinstance(per_question, list):
        return None
    values: list[float] = []
    for entry in per_question:
        if not isinstance(entry, dict):
            continue
        n = _num(entry.get("time_working_ms"))
        if n is not None:
            values.append(n)
    return _avg(values)


def _activated_from_summary(summary: dict[str, Any]) -> bool:
    explicit = summary.get("activated")
    if isinstance(explicit, bool):
        return explicit
    return _int(summary.get("capture_count")) > 0 or _int(summary.get("oral_transcript_count")) > 0


def _str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _load_summary_for_session(session_dir: Path) -> tuple[dict[str, Any] | None, bool]:
    """
    Return (summary dict, recovered_from_events).
    Falls back to events.jsonl when summary.json is missing or empty.
    """
    summary_path = session_dir / "summary.json"
    summary = _load_json(summary_path)
    if summary is not None:
        return summary, False

    events_path = session_dir / "events.jsonl"
    if not events_path.is_file() or events_path.stat().st_size == 0:
        return None, False

    session_id = session_dir.name
    events = metrics_log.read_events(events_path)
    if not events:
        return None, False

    summary = build_metrics_summary(
        session_id,
        events,
        sessions_root=settings.JETSON_SESSIONS_ROOT,
    )
    metrics_log.write_summary(events_path, summary=summary)
    return summary, True


def _session_row_from_files(session_dir: Path) -> tuple[schemas.StudyDashboardSessionRow | None, bool]:
    summary, _recovered = _load_summary_for_session(session_dir)
    if summary is None:
        summary_path = session_dir / "summary.json"
        events_path = session_dir / "events.jsonl"
        has_placeholder = summary_path.exists() or events_path.exists()
        return None, has_placeholder

    snapshot = _load_json(session_dir / "session_snapshot.json") or {}
    study_plan = snapshot.get("study_plan") if isinstance(snapshot.get("study_plan"), dict) else {}
    survey = snapshot.get("survey") if isinstance(snapshot.get("survey"), dict) else None
    if survey is None:
        survey = _load_json(session_dir / "survey_answers.json") or {}
    path_student_id = session_dir.parent.parent.parent.parent.name
    path_day_run_id = session_dir.parent.parent.name

    return (
        schemas.StudyDashboardSessionRow(
            session_id=str(summary.get("session_id") or snapshot.get("session_id") or session_dir.name),
            student_id=str(snapshot.get("student_id") or path_student_id),
            day_run_id=str(snapshot.get("day_run_id") or path_day_run_id),
            course=str(study_plan.get("course") or ""),
            topic_id=str(study_plan.get("topic_id") or ""),
            requested_count=_int(study_plan.get("requested_count")) if study_plan.get("requested_count") is not None else None,
            event_count=_int(summary.get("event_count")),
            study_sessions_started=_int(summary.get("study_sessions_started")),
            question_count=_int(summary.get("question_count")),
            capture_count=_int(summary.get("capture_count")),
            activated=_activated_from_summary(summary),
            ama_user_count=_int(summary.get("ama_user_count")),
            grade_count=_int(summary.get("grade_count")),
            session_completed=bool(summary.get("session_completed")),
            reached_post_session_summary=bool(summary.get("reached_post_session_summary")),
            survey_submitted=bool(summary.get("survey_submitted")),
            survey_helpfulness=_num(summary.get("survey_helpfulness")),
            survey_ease_of_use=_num(summary.get("survey_ease_of_use")),
            survey_question_difficulty=_num(summary.get("survey_question_difficulty")),
            survey_would_use_again=summary.get("survey_would_use_again")
            if isinstance(summary.get("survey_would_use_again"), bool)
            else None,
            survey_liked=_str(survey.get("liked")),
            survey_disliked=_str(survey.get("disliked")),
            survey_improvements=_str(survey.get("improvements")),
            survey_anything_else=_str(survey.get("anything_else")),
            survey_response_feedback=_str(survey.get("response_feedback")),
            session_duration_ms=_int(summary.get("session_duration_ms")) if summary.get("session_duration_ms") is not None else None,
            avg_grade_duration_ms=_num(summary.get("avg_grade_duration_ms")),
            time_to_first_capture_ms=_int(summary.get("time_to_first_capture_ms"))
            if summary.get("time_to_first_capture_ms") is not None
            else None,
            avg_time_working_ms=_avg_time_working_ms(summary),
            percent_correct_questions=_num(summary.get("percent_correct_questions")),
            questions_with_repeat_attempts=_int(summary.get("questions_with_repeat_attempts")),
            backend_error_count=_int(summary.get("backend_error_count")),
            client_error_count=_int(summary.get("client_error_count")),
            jetson_backend_error_rate=_percent_rate(summary.get("jetson_backend_error_rate")),
            questions_answered_oral=_int(summary.get("questions_answered_oral")),
            questions_answered_paper=_int(summary.get("questions_answered_paper")),
            oral_upload_count=_int(summary.get("oral_upload_count")),
            oral_transcript_count=_int(summary.get("oral_transcript_count")),
            oral_retake_count=_int(summary.get("oral_retake_count")),
            oral_record_started_count=_int(summary.get("oral_record_started_count")),
            avg_oral_record_duration_ms=_num(summary.get("avg_oral_record_duration_ms")),
            avg_transcription_duration_ms=_num(summary.get("avg_transcription_duration_ms")),
            upload_to_transcript_ms=_num(summary.get("avg_upload_to_transcript_ms")),
            avg_paper_grade_duration_ms=_num(summary.get("avg_paper_grade_duration_ms")),
            avg_oral_grade_duration_ms=_num(summary.get("avg_oral_grade_duration_ms")),
            oral_transcript_total_chars=_int(summary.get("oral_transcript_total_chars")),
        ),
        False,
    )


def _build_totals(rows: list[schemas.StudyDashboardSessionRow]) -> schemas.StudyDashboardTotals:
    session_count = len(rows)
    study_sessions_started = sum(row.study_sessions_started for row in rows) or session_count
    activated = sum(1 for row in rows if row.activated)
    completed = sum(1 for row in rows if row.session_completed)
    reached_summary = sum(1 for row in rows if row.reached_post_session_summary)
    survey_submissions = sum(1 for row in rows if row.survey_submitted)
    repeated_usage_yes = sum(1 for row in rows if row.survey_would_use_again is True)
    repeated_usage_responses = sum(1 for row in rows if row.survey_would_use_again is not None)
    return schemas.StudyDashboardTotals(
        sessions=session_count,
        study_sessions_started=study_sessions_started,
        students=len({row.student_id for row in rows if row.student_id}),
        activated_sessions=activated,
        activation_rate=_rate(activated, study_sessions_started),
        completed_sessions=completed,
        completion_rate=_rate(completed, session_count),
        reached_post_session_summary_count=reached_summary,
        reached_post_session_summary_rate=_rate(reached_summary, session_count),
        survey_submissions=survey_submissions,
        survey_submit_rate=_rate(survey_submissions, session_count),
        repeated_usage_yes_count=repeated_usage_yes,
        repeated_usage_response_count=repeated_usage_responses,
        repeated_usage_rate=_rate(repeated_usage_yes, repeated_usage_responses)
        if repeated_usage_responses
        else None,
        avg_helpfulness=_avg(row.survey_helpfulness for row in rows),
        avg_ease_of_use=_avg(row.survey_ease_of_use for row in rows),
        avg_question_difficulty=_avg(row.survey_question_difficulty for row in rows),
        avg_session_duration_ms=_avg(row.session_duration_ms for row in rows),
        avg_grade_duration_ms=_avg(row.avg_grade_duration_ms for row in rows),
        avg_time_to_first_capture_ms=_avg(row.time_to_first_capture_ms for row in rows),
        avg_time_working_ms=_avg(row.avg_time_working_ms for row in rows),
        avg_questions_per_session=_avg(row.question_count for row in rows),
        avg_percent_correct_questions=_avg(row.percent_correct_questions for row in rows),
        jetson_backend_error_rate=_avg(row.jetson_backend_error_rate for row in rows),
        total_questions=sum(row.question_count for row in rows),
        total_captures=sum(row.capture_count for row in rows),
        total_ama_turns=sum(row.ama_user_count for row in rows),
        backend_error_count=sum(row.backend_error_count for row in rows),
        client_error_count=sum(row.client_error_count for row in rows),
        questions_answered_oral=sum(row.questions_answered_oral for row in rows),
        questions_answered_paper=sum(row.questions_answered_paper for row in rows),
        oral_upload_count=sum(row.oral_upload_count for row in rows),
        oral_transcript_count=sum(row.oral_transcript_count for row in rows),
        oral_retake_count=sum(row.oral_retake_count for row in rows),
        oral_record_started_count=sum(row.oral_record_started_count for row in rows),
        avg_oral_record_duration_ms=_avg(row.avg_oral_record_duration_ms for row in rows),
        avg_transcription_duration_ms=_avg(row.avg_transcription_duration_ms for row in rows),
        p95_transcription_duration_ms=None,
        avg_upload_to_transcript_ms=_avg(row.upload_to_transcript_ms for row in rows),
        avg_paper_grade_duration_ms=_avg(row.avg_paper_grade_duration_ms for row in rows),
        avg_oral_grade_duration_ms=_avg(row.avg_oral_grade_duration_ms for row in rows),
        p95_oral_grade_duration_ms=None,
        oral_transcript_total_chars=sum(row.oral_transcript_total_chars for row in rows),
    )


def _build_topics(rows: list[schemas.StudyDashboardSessionRow]) -> list[schemas.StudyDashboardTopicRow]:
    buckets: dict[tuple[str, str], list[schemas.StudyDashboardSessionRow]] = {}
    for row in rows:
        key = (row.course or "Unknown", row.topic_id or "Unknown")
        buckets.setdefault(key, []).append(row)

    topics: list[schemas.StudyDashboardTopicRow] = []
    for (course, topic_id), group in buckets.items():
        completed = sum(1 for row in group if row.session_completed)
        topics.append(
            schemas.StudyDashboardTopicRow(
                course=course,
                topic_id=topic_id,
                sessions=len(group),
                completion_rate=_rate(completed, len(group)),
                avg_helpfulness=_avg(row.survey_helpfulness for row in group),
                avg_percent_correct_questions=_avg(row.percent_correct_questions for row in group),
                avg_grade_duration_ms=_avg(row.avg_grade_duration_ms for row in group),
                questions_answered_oral=sum(row.questions_answered_oral for row in group),
                questions_answered_paper=sum(row.questions_answered_paper for row in group),
                oral_transcript_count=sum(row.oral_transcript_count for row in group),
                avg_transcription_duration_ms=_avg(row.avg_transcription_duration_ms for row in group),
                avg_oral_grade_duration_ms=_avg(row.avg_oral_grade_duration_ms for row in group),
            )
        )
    return sorted(topics, key=lambda row: (-row.sessions, row.course, row.topic_id))


@router.get("/summary", response_model=schemas.StudyDashboardSummary)
def get_study_dashboard_summary() -> schemas.StudyDashboardSummary:
    root = _metrics_root()
    rows: list[schemas.StudyDashboardSessionRow] = []
    malformed = 0

    if root.is_dir():
        session_dirs: set[Path] = set()
        for events_path in root.glob("students/*/day_runs/*/sessions/*/events.jsonl"):
            if events_path.stat().st_size > 0:
                session_dirs.add(events_path.parent)
        for summary_path in root.glob("students/*/day_runs/*/sessions/*/summary.json"):
            session_dirs.add(summary_path.parent)

        for session_dir in sorted(session_dirs):
            row, bad = _session_row_from_files(session_dir)
            if row is not None:
                rows.append(row)
            elif bad:
                malformed += 1

    rows.sort(key=lambda row: (row.day_run_id, row.student_id, row.session_id), reverse=True)
    return schemas.StudyDashboardSummary(
        generated_at=datetime.utcnow(),
        source_root=str(root),
        totals=_build_totals(rows),
        sessions=rows,
        topics=_build_topics(rows),
        malformed_files=malformed,
    )
