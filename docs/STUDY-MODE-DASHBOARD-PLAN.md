# Study Mode Dashboard Plan

## Goal

Build a teacher-facing dashboard that turns existing Study Mode telemetry into actionable session, student, and product insights. The first version should avoid changing the live study flow and should read from artifacts already produced by the Jetson runtime:

- `jetson_runtime/metrics/students/<student_id>/day_runs/<day_run_id>/sessions/<session_id>/summary.json`
- `jetson_runtime/metrics/students/<student_id>/day_runs/<day_run_id>/sessions/<session_id>/session_snapshot.json`
- `jetson_runtime/metrics/students/<student_id>/day_runs/<day_run_id>/sessions/<session_id>/survey_answers.json`
- `jetson_runtime/sessions/<session_id>/paper/interactions.jsonl` for later drill-down when needed

## Current Data Sources

### Central Backend

The central backend owns durable `sessions` rows. For Study Mode, each session can include:

- `student_id`
- `device_info.source = "web-student-ui"`
- `device_info.mode = "study"`
- `device_info.study_plan`
- `artifacts.mode = "study"`
- `artifacts.session_dir_uri`
- `artifacts.study_feedback`
- `artifacts.study_teacher_summary`
- survey completion markers such as `study_survey_completed` and `study_survey_skipped`

This is useful for joining Study Mode runs to central session records, but it does not currently contain the detailed event timeline.

### Jetson Metrics Mirror

The metrics mirror is the best first dashboard source. It is already student/day/session oriented and includes derived metrics in `summary.json`, plus richer drill-down material in `session_snapshot.json`.

Useful `summary.json` fields:

- `event_count`
- `question_count`
- `capture_count`
- `ama_user_count`
- `grade_count`
- `avg_grade_duration_ms`
- `max_grade_duration_ms`
- `p95_grade_duration_ms`
- `session_duration_ms`
- `time_to_first_capture_ms`
- `activated`
- `session_completed`
- `reached_post_session_summary`
- `survey_submitted`
- `survey_helpfulness`
- `survey_ease_of_use`
- `survey_question_difficulty`
- `survey_would_use_again`
- `client_event_counts`
- `backend_error_count`
- `client_error_count`
- `percent_correct_questions`
- `questions_with_repeat_attempts`
- `per_question`

Useful `session_snapshot.json` fields:

- `student_id`
- `day_run_id`
- `study_plan.course`
- `study_plan.topic_id`
- `study_plan.requested_count`
- `question_specs`
- `captures_by_question`
- `ama_transcript`
- `study_feedback`
- `survey`
- `paper_dir`
- `interactions_path`

## Version 1 Scope

Version 1 should provide a read-only teacher dashboard at `/teacher/study-dashboard`.

### Backend

Add a central backend route:

`GET /study-dashboard/summary`

The endpoint should:

- Walk `settings.JETSON_SESSIONS_ROOT.parent / "metrics" / "students"`.
- Read each session's `summary.json`.
- Read `session_snapshot.json` when present.
- Normalize each session into a compact JSON row.
- Compute dashboard-level rollups.
- Never fail the whole response because one session file is malformed.

Initial response shape:

```json
{
  "generated_at": "2026-05-11T00:00:00Z",
  "source_root": ".../jetson_runtime/metrics",
  "totals": {
    "sessions": 0,
    "students": 0,
    "activated_sessions": 0,
    "activation_rate": 0,
    "completed_sessions": 0,
    "completion_rate": 0,
    "survey_submissions": 0,
    "survey_submit_rate": 0,
    "avg_helpfulness": null,
    "avg_ease_of_use": null,
    "avg_question_difficulty": null,
    "avg_session_duration_ms": null,
    "avg_grade_duration_ms": null,
    "avg_time_to_first_capture_ms": null,
    "total_questions": 0,
    "total_captures": 0,
    "total_ama_turns": 0,
    "backend_error_count": 0,
    "client_error_count": 0
  },
  "sessions": [
    {
      "session_id": "sess-...",
      "student_id": "2111",
      "day_run_id": "2026-04-30",
      "course": "CS109",
      "topic_id": "conditional_probability",
      "requested_count": 2,
      "question_count": 2,
      "capture_count": 1,
      "activated": true,
      "ama_user_count": 2,
      "grade_count": 1,
      "session_completed": true,
      "reached_post_session_summary": true,
      "survey_submitted": true,
      "survey_helpfulness": 5,
      "survey_ease_of_use": 5,
      "survey_question_difficulty": 3,
      "survey_would_use_again": true,
      "session_duration_ms": 387567,
      "avg_grade_duration_ms": 8220,
      "time_to_first_capture_ms": 241376,
      "percent_correct_questions": 0,
      "questions_with_repeat_attempts": 0,
      "backend_error_count": 0,
      "client_error_count": 0
    }
  ],
  "topics": [
    {
      "course": "CS109",
      "topic_id": "conditional_probability",
      "sessions": 0,
      "completion_rate": 0,
      "avg_helpfulness": null,
      "avg_percent_correct_questions": null,
      "avg_grade_duration_ms": null
    }
  ]
}
```

### Frontend

Add:

- `web/src/types/studyDashboard.ts`
- `web/src/api/studyDashboard.ts`
- `web/src/pages/TeacherStudyDashboardPage.tsx`
- `web/src/pages/TeacherStudyDashboardPage.module.css`
- route constant `ROUTE_PATH.TEACHER_STUDY_DASHBOARD`
- authenticated route in `App.tsx`
- link from the teacher home page

Version 1 UI sections:

- KPI cards for sessions, students, activation, completion, survey submit rate, average helpfulness, average grade latency.
- Funnel summary: started, activated, completed, review reached, survey submitted.
- Topic table: course/topic sessions, completion, helpfulness, correctness, latency.
- Recent sessions table: student, day, course/topic, questions, captures, AMA turns, completion, survey, timing, errors.

## Version 2 Scope

After the first read-only dashboard works, add:

- Date, student, course, topic, and completion filters.
- Session drill-down with teacher summary, flags, action items, AMA transcript, and capture thumbnails.
- Survey qualitative view grouped by liked, disliked, improvements, and response feedback.
- Export as CSV.
- Optional daily student rollups using `day_run_id`.

## Implementation Order

1. Add this plan document.
2. Add backend schemas for dashboard totals, session rows, and topic rows.
3. Add `backend/routes/study_dashboard.py`.
4. Register the route in `backend/routes/__init__.py`.
5. Add frontend dashboard types and API client.
6. Add the teacher dashboard page.
7. Add route and teacher home link.
8. Run backend import/tests and frontend typecheck/lint where possible.

## Notes And Risks

- Some metrics files contain absolute paths from the Jetson machine; the dashboard should display counts and metadata first, not assume image paths are web-accessible.
- `summary.json` may be absent for runs that did not reach `/end`; later versions can recover by parsing `events.jsonl`.
- The current metrics mirror is local to the central backend filesystem only when the Jetson sessions/metrics directory is mounted or available on the same machine.
- Survey data is optional, so averages must ignore nulls and clearly show submission rate.
- The dashboard should not expose raw student IDs outside teacher-authenticated routes.
