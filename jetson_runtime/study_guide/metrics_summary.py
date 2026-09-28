"""Roll up metrics JSONL events into a session summary dict."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from study_guide import study_answer


def build_metrics_summary(
    session_id: str,
    events: list[dict[str, Any]],
    *,
    sessions_root: Path | None = None,
) -> dict[str, Any]:
    def _p95(values: list[int]) -> int | None:
        if not values:
            return None
        xs = sorted(values)
        idx = max(0, int((len(xs) * 0.95 + 0.999999)) - 1)
        return xs[idx]

    capture_count = sum(1 for e in events if e.get("type") == "capture")
    ama_user_count = sum(1 for e in events if e.get("type") == "ama_turn" and e.get("role") == "user")
    grade_durations = [
        int(e.get("duration_ms"))
        for e in events
        if e.get("type") == "grade_completed" and isinstance(e.get("duration_ms"), (int, float))
    ]
    paper_grade_durations = [
        int(e.get("duration_ms"))
        for e in events
        if e.get("type") == "grade_completed"
        and e.get("source") == "paper"
        and isinstance(e.get("duration_ms"), (int, float))
    ]
    oral_grade_durations = [
        int(e.get("duration_ms"))
        for e in events
        if e.get("type") == "grade_completed"
        and e.get("source") == "oral"
        and isinstance(e.get("duration_ms"), (int, float))
    ]
    transcription_durations = [
        int(e.get("transcription_duration_ms"))
        for e in events
        if e.get("type") == "oral_transcript"
        and isinstance(e.get("transcription_duration_ms"), (int, float))
    ]
    upload_to_transcript_ms_list = [
        int(e.get("upload_to_transcript_ms"))
        for e in events
        if e.get("type") == "oral_transcript"
        and isinstance(e.get("upload_to_transcript_ms"), (int, float))
    ]
    oral_transcript_events = [e for e in events if e.get("type") == "oral_transcript"]
    oral_upload_count = sum(1 for e in events if e.get("type") == "oral_upload_started")
    oral_transcript_count = len(oral_transcript_events)
    oral_retake_count = sum(1 for e in events if e.get("type") == "oral_retake")
    activated = capture_count > 0 or oral_transcript_count > 0
    answer_mode_by_q: dict[int, str] = {}
    for e in events:
        if e.get("type") != "answer_mode_set":
            continue
        qi = e.get("question_index")
        mode = e.get("mode")
        if isinstance(qi, int) and mode in ("paper", "oral"):
            answer_mode_by_q[qi] = mode
    if sessions_root is not None:
        paper_modes_path = sessions_root / session_id / "paper"
        if paper_modes_path.is_dir():
            for k, mode in study_answer.load_answer_modes(paper_modes_path).items():
                try:
                    qi = int(k)
                except ValueError:
                    continue
                if mode in ("paper", "oral") and qi not in answer_mode_by_q:
                    answer_mode_by_q[qi] = mode
    oral_record_started = sum(
        1 for e in events if e.get("type") == "client_event" and e.get("client_event_type") == "oral_record_started"
    )
    oral_record_stopped = sum(
        1 for e in events if e.get("type") == "client_event" and e.get("client_event_type") == "oral_record_stopped"
    )
    oral_record_durations_ms = [
        int((e.get("data") or {}).get("record_duration_ms"))
        for e in events
        if e.get("type") == "client_event"
        and e.get("client_event_type") == "oral_record_stopped"
        and isinstance((e.get("data") or {}).get("record_duration_ms"), (int, float))
    ]
    question_indices = sorted(
        {
            int(e.get("question_index"))
            for e in events
            if isinstance(e.get("question_index"), int) and e.get("type") == "question_shown"
        }
    )
    per_question: list[dict[str, Any]] = []
    question_shown_ts: dict[int, float] = {}
    question_done_ts: dict[int, float] = {}
    question_grade_req_ts: dict[int, float] = {}
    question_correctness: dict[int, str] = {}
    grade_requested_counts: dict[int, int] = {}
    for e in events:
        qi = e.get("question_index")
        if not isinstance(qi, int):
            continue
        if e.get("type") == "question_shown" and qi not in question_shown_ts:
            question_shown_ts[qi] = float(e.get("ts", 0))
        if e.get("type") == "grade_requested" and qi not in question_grade_req_ts:
            question_grade_req_ts[qi] = float(e.get("ts", 0))
        if e.get("type") == "grade_requested":
            grade_requested_counts[qi] = grade_requested_counts.get(qi, 0) + 1
        if e.get("type") in ("capture_feedback", "oral_feedback"):
            feedback_json = e.get("feedback_json")
            if isinstance(feedback_json, dict):
                correctness = feedback_json.get("correctness")
                if isinstance(correctness, str) and correctness.strip():
                    question_correctness[qi] = correctness.strip().lower()
        if e.get("type") == "grade_completed" and e.get("ok") is True:
            question_done_ts[qi] = float(e.get("ts", 0))
    correctness_scored = 0
    correctness_correct = 0
    correctness_partial = 0
    correctness_unclear = 0
    for qi in question_indices:
        start = question_shown_ts.get(qi)
        req = question_grade_req_ts.get(qi)
        end = question_done_ts.get(qi)
        correctness = question_correctness.get(qi)
        if correctness:
            correctness_scored += 1
            if correctness in ("correct", "mostly_correct", "right"):
                correctness_correct += 1
            elif correctness in ("partial", "partially_correct"):
                correctness_partial += 1
            else:
                correctness_unclear += 1
        q_mode = answer_mode_by_q.get(qi, "paper")
        oral_ev = next(
            (e for e in oral_transcript_events if e.get("question_index") == qi),
            None,
        )
        per_question.append(
            {
                "question_index": qi,
                "answer_mode": q_mode,
                "time_to_grade_ms": int((end - start) * 1000) if start and end and end >= start else None,
                "time_working_ms": int((req - start) * 1000) if start and req and req >= start else None,
                "time_waiting_ms": int((end - req) * 1000) if req and end and end >= req else None,
                "grade_attempt_count": grade_requested_counts.get(qi, 0),
                "repeat_attempted": grade_requested_counts.get(qi, 0) > 1,
                "capture_count": sum(
                    1 for e in events if e.get("type") == "capture" and e.get("question_index") == qi
                ),
                "ama_count": sum(
                    1
                    for e in events
                    if e.get("type") == "ama_turn"
                    and e.get("role") == "user"
                    and e.get("question_index") == qi
                ),
                "oral_transcript_char_count": oral_ev.get("transcript_char_count") if oral_ev else None,
                "oral_transcript_word_count": oral_ev.get("transcript_word_count") if oral_ev else None,
                "transcription_duration_ms": oral_ev.get("transcription_duration_ms") if oral_ev else None,
                "upload_to_transcript_ms": oral_ev.get("upload_to_transcript_ms") if oral_ev else None,
                "oral_record_duration_ms": next(
                    (
                        int((e.get("data") or {}).get("record_duration_ms"))
                        for e in events
                        if e.get("type") == "client_event"
                        and e.get("client_event_type") == "oral_record_stopped"
                        and e.get("question_index") == qi
                        and isinstance((e.get("data") or {}).get("record_duration_ms"), (int, float))
                    ),
                    None,
                ),
                "correctness": correctness,
            }
        )
    run_started_ts = next((float(e.get("ts", 0)) for e in events if e.get("type") == "run_started"), None)
    run_ended_ts = next((float(e.get("ts", 0)) for e in events if e.get("type") == "run_ended"), None)
    first_capture_ts = next((float(e.get("ts", 0)) for e in events if e.get("type") == "capture"), None)
    client_events = [e for e in events if e.get("type") == "client_event"]
    client_event_counts: dict[str, int] = {}
    total_scroll_events = 0
    total_scroll_delta_y_px = 0
    total_pointer_moves = 0
    total_pointer_distance_px = 0
    max_scroll_y_px = 0
    for e in client_events:
        et = str(e.get("client_event_type") or "")
        if et:
            client_event_counts[et] = client_event_counts.get(et, 0) + 1
        data = e.get("data")
        if not isinstance(data, dict):
            continue
        sev = data.get("scroll_event_count")
        sdy = data.get("scroll_delta_y_px")
        pm = data.get("pointer_move_count")
        pd = data.get("pointer_distance_px")
        msy = data.get("max_scroll_y_px")
        if isinstance(sev, (int, float)):
            total_scroll_events += int(sev)
        if isinstance(sdy, (int, float)):
            total_scroll_delta_y_px += int(sdy)
        if isinstance(pm, (int, float)):
            total_pointer_moves += int(pm)
        if isinstance(pd, (int, float)):
            total_pointer_distance_px += int(pd)
        if isinstance(msy, (int, float)):
            max_scroll_y_px = max(max_scroll_y_px, int(msy))

    survey_event = next((e for e in events if e.get("type") == "survey_submitted"), None)
    run_ended_count = sum(1 for e in events if e.get("type") == "run_ended")
    backend_error_count = sum(
        1
        for e in events
        if (
            str(e.get("type", "")).endswith("_error")
            or e.get("type") == "capture_failed"
            or (e.get("type") == "grade_completed" and e.get("ok") is False)
        )
    )
    client_error_count = sum(
        1
        for e in client_events
        if str(e.get("client_event_type", "")).endswith("_error")
    )
    reached_post_session_summary = (
        client_event_counts.get("review_page_viewed", 0) > 0
        or client_event_counts.get("review_feedback_ready", 0) > 0
        or client_event_counts.get("review_finish_clicked", 0) > 0
    )
    return {
        "session_id": session_id,
        "event_count": len(events),
        "question_count": len(question_indices),
        "capture_count": capture_count,
        "activated": activated,
        "ama_user_count": ama_user_count,
        "grade_count": len(grade_durations),
        "avg_grade_duration_ms": int(sum(grade_durations) / len(grade_durations)) if grade_durations else None,
        "max_grade_duration_ms": max(grade_durations) if grade_durations else None,
        "p95_grade_duration_ms": _p95(grade_durations),
        "session_duration_ms": int((run_ended_ts - run_started_ts) * 1000)
        if run_started_ts and run_ended_ts and run_ended_ts >= run_started_ts
        else None,
        "time_to_first_capture_ms": int((first_capture_ts - run_started_ts) * 1000)
        if run_started_ts and first_capture_ts and first_capture_ts >= run_started_ts
        else None,
        "run_ended_count": run_ended_count,
        "study_sessions_started": 1 if run_started_ts else 0,
        "session_completed": run_ended_count > 0,
        "reached_post_session_summary": reached_post_session_summary,
        "survey_submitted": survey_event is not None,
        "survey_helpfulness": survey_event.get("helpfulness") if isinstance(survey_event, dict) else None,
        "survey_ease_of_use": survey_event.get("ease_of_use") if isinstance(survey_event, dict) else None,
        "survey_question_difficulty": survey_event.get("question_difficulty") if isinstance(survey_event, dict) else None,
        "survey_would_use_again": survey_event.get("would_use_again") if isinstance(survey_event, dict) else None,
        "client_event_counts": client_event_counts,
        "total_scroll_events": total_scroll_events,
        "total_scroll_delta_y_px": total_scroll_delta_y_px,
        "max_scroll_y_px": max_scroll_y_px,
        "total_pointer_moves": total_pointer_moves,
        "total_pointer_distance_px": total_pointer_distance_px,
        "backend_error_count": backend_error_count,
        "client_error_count": client_error_count,
        "jetson_backend_error_rate": (backend_error_count / len(events)) if events else None,
        "correctness_scored_questions": correctness_scored,
        "correctness_correct_questions": correctness_correct,
        "correctness_partial_questions": correctness_partial,
        "correctness_unclear_questions": correctness_unclear,
        "percent_correct_questions": round((correctness_correct / correctness_scored) * 100, 2)
        if correctness_scored
        else None,
        "questions_with_repeat_attempts": sum(1 for q in question_indices if grade_requested_counts.get(q, 0) > 1),
        "per_question": per_question,
        "questions_answered_oral": sum(1 for m in answer_mode_by_q.values() if m == "oral"),
        "questions_answered_paper": sum(1 for m in answer_mode_by_q.values() if m == "paper"),
        "oral_upload_count": oral_upload_count,
        "oral_transcript_count": oral_transcript_count,
        "oral_retake_count": oral_retake_count,
        "oral_record_started_count": oral_record_started,
        "oral_record_stopped_count": oral_record_stopped,
        "avg_oral_record_duration_ms": int(sum(oral_record_durations_ms) / len(oral_record_durations_ms))
        if oral_record_durations_ms
        else None,
        "avg_transcription_duration_ms": int(sum(transcription_durations) / len(transcription_durations))
        if transcription_durations
        else None,
        "max_transcription_duration_ms": max(transcription_durations) if transcription_durations else None,
        "p95_transcription_duration_ms": _p95(transcription_durations),
        "avg_upload_to_transcript_ms": int(sum(upload_to_transcript_ms_list) / len(upload_to_transcript_ms_list))
        if upload_to_transcript_ms_list
        else None,
        "p95_upload_to_transcript_ms": _p95(upload_to_transcript_ms_list),
        "avg_paper_grade_duration_ms": int(sum(paper_grade_durations) / len(paper_grade_durations))
        if paper_grade_durations
        else None,
        "avg_oral_grade_duration_ms": int(sum(oral_grade_durations) / len(oral_grade_durations))
        if oral_grade_durations
        else None,
        "max_oral_grade_duration_ms": max(oral_grade_durations) if oral_grade_durations else None,
        "p95_oral_grade_duration_ms": _p95(oral_grade_durations),
        "oral_transcript_total_chars": sum(
            int(e.get("transcript_char_count") or 0) for e in oral_transcript_events
        ),
        "oral_transcripts": [
            {
                "question_index": e.get("question_index"),
                "transcript": e.get("transcript"),
                "transcript_char_count": e.get("transcript_char_count"),
                "transcription_duration_ms": e.get("transcription_duration_ms"),
                "upload_to_transcript_ms": e.get("upload_to_transcript_ms"),
            }
            for e in oral_transcript_events
        ],
    }
