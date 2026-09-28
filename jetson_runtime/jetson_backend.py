"""
Jetson-local FastAPI backend that wraps jetson_runtime OralExamProctor.

This service exposes a minimal HTTP API for the student web UI:

- POST /jetson/exams
    Starts an exam for a given session_id and exam config.
- GET /jetson/exams/{session_id}/state
    Returns coarse exam state suitable for the UI status pill.
- POST /jetson/exams/{session_id}/stop
    Requests early termination of the running exam.

For MVP, state is approximate and driven by coarse phases of the proctor.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

import os
import requests
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import settings
from proctor import OralExamProctor
from study_guide import session_log
from study_guide import metrics_log
from study_guide.metrics_summary import build_metrics_summary
from study_guide.feedback_aggregation import aggregate_study_session
from study_guide.paper_capture import capture_paper_image
from study_guide.student_summary import (
    build_study_student_feedback,
    build_study_student_feedback_multi,
)
from study_guide.teacher_summary import (
    build_study_teacher_summary,
    build_study_teacher_summary_multi,
)
from study_guide.ama_prompt import build_study_ama_prompt
from study_guide.oral_feedback import request_oral_feedback
from study_guide import study_answer
from study_guide.vision_feedback import request_paper_feedback
from tts.tts_client import get_tts_client


ExamStatus = Literal["idle", "listening", "speaking", "thinking", "done"]
StudyStatus = Literal["idle", "capturing", "thinking", "done", "error"]


class CreateExamRequest(BaseModel):
    session_id: str
    exam_config_path: Optional[str] = None
    exam_config: Optional[dict[str, Any]] = None


class CreateExamResponse(BaseModel):
    session_id: str


class ExamState(BaseModel):
    session_id: str
    status: ExamStatus
    questionText: str
    transcriptPreview: str


class PracticeQuestionPayload(BaseModel):
    """One practice item from the central question-bank selection API."""

    id: str = ""
    text: str
    rubric_items: list[str]
    difficulty: Optional[str] = None
    hints: list[str] = Field(default_factory=list)


class CreateStudyRunRequest(BaseModel):
    session_id: str
    student_id: Optional[str] = None
    day_run_id: Optional[str] = None
    study_plan: Optional[dict[str, Any]] = None
    # Either provide an exam_config (same schema as oral exam) and we take the first question,
    # or provide question_text/rubric_items directly for study mode.
    exam_config: Optional[dict[str, Any]] = None
    question_text: Optional[str] = None
    rubric_items: Optional[list[str]] = None
    # When non-empty, takes precedence over exam_config / question_text (question-bank study).
    practice_questions: Optional[list[PracticeQuestionPayload]] = None


class CreateStudyRunResponse(BaseModel):
    session_id: str


class AmaTurnModel(BaseModel):
    role: str
    content: str


class StudyRunState(BaseModel):
    session_id: str
    status: StudyStatus
    questionText: str
    feedbackMarkdown: str
    followUpMarkdown: str
    latestImageUrl: str
    error: str
    captureCount: int = 0
    captureLimit: int = 5
    questionIndex: int = 1
    questionCount: int = 1
    hints: list[str] = Field(default_factory=list)
    ama_turns: list[AmaTurnModel] = Field(default_factory=list)
    answerMode: Literal["paper", "oral"] = "paper"
    oralTranscript: str = ""
    oralHasRecording: bool = False


class CaptureRequest(BaseModel):
    width: int = 1280
    height: int = 720


class GradeRequest(BaseModel):
    """Grade the current question using all captured images (up to captureLimit)."""

    # Reserved for future knobs (e.g. "force": bool, "max_images": int)
    pass


class SetAnswerModeRequest(BaseModel):
    mode: Literal["paper", "oral"]


class StudyActionRequest(BaseModel):
    action: Literal["understand", "lost", "question", "ama"]
    questionText: Optional[str] = None


class StudyExitSurveyRequest(BaseModel):
    """Payload for the optional end-of-study exit survey.

    All fields are optional: the frontend only POSTs when at least one
    answer is provided (an all-empty survey is treated as "skipped" client
    side and never reaches this endpoint). Likert ratings, when present,
    must be integers in ``[1, 5]``.
    """

    helpfulness: Optional[int] = None
    ease_of_use: Optional[int] = None
    question_difficulty: Optional[int] = None
    would_use_again: Optional[bool] = None
    liked: str = ""
    disliked: str = ""
    improvements: str = ""
    anything_else: str = ""
    response_feedback: str = ""


class StudyClientEventRequest(BaseModel):
    """
    Telemetry emitted by the student web UI (visibility changes, unloads, client errors, etc.).
    """

    type: str
    question_index: Optional[int] = None
    data: dict[str, Any] = Field(default_factory=dict)
    client_ts_ms: Optional[int] = None


@dataclass
class _ExamRuntime:
    session_id: str
    proctor: OralExamProctor
    thread: threading.Thread
    status: ExamStatus = "idle"
    current_question: str = ""
    transcript_preview: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    central_session_id: str | None = None


@dataclass(frozen=True)
class _StudyQuestionSpec:
    qid: str
    text: str
    rubric_items: list[str]
    difficulty: str = ""
    hints: list[str] = field(default_factory=list)


@dataclass
class _StudyRuntime:
    session_id: str
    student_id: str = ""
    day_run_id: str = ""
    study_plan: dict[str, Any] | None = None
    status: StudyStatus = "idle"
    question_text: str = ""
    rubric_items: list[str] = None  # type: ignore[assignment]
    hints: list[str] = field(default_factory=list)
    question_specs: list[_StudyQuestionSpec] = field(default_factory=list)
    current_index: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_image_path: str = ""
    last_image_url: str = ""
    feedback_md: str = ""
    feedback_json: dict[str, Any] | None = None
    followup_md: str = ""
    error: str = ""
    thread: threading.Thread | None = None
    ama_turns: list[dict[str, str]] = field(default_factory=list)


def _current_answer_mode(runtime: _StudyRuntime) -> study_answer.AnswerMode:
    return study_answer.get_answer_mode(_study_paper_dir(runtime.session_id), runtime.current_index)


def _oral_transcript_for_runtime(runtime: _StudyRuntime) -> tuple[str, bool]:
    text, _ = study_answer.load_oral_transcript(
        _study_paper_dir(runtime.session_id), runtime.current_index
    )
    return text, bool(text.strip())


def _build_study_ama_context(runtime: _StudyRuntime) -> str:
    """Static snapshot of the whole study session for the tutor model."""
    specs = runtime.question_specs or []
    n = max(len(specs), 1)
    idx = runtime.current_index
    parts: list[str] = []
    parts.append("## Session overview")
    parts.append(f"- Session id: {runtime.session_id}")
    parts.append(f"- Current position: question {idx + 1} of {n} (0-based index {idx}).")
    parts.append("")
    parts.append("## Every question in this practice run")
    if not specs:
        parts.append("(Single-question run.)")
        parts.append("")
        parts.append(runtime.question_text or "")
        rub = runtime.rubric_items or []
        if rub:
            parts.append("Rubric / expectations:")
            parts.extend(f"- {r}" for r in rub)
        if runtime.hints:
            parts.append("Progressive hints:")
            parts.extend(f"- {h}" for h in runtime.hints)
    else:
        for i, spec in enumerate(specs):
            mark = " **← student is here now**" if i == idx else ""
            parts.append(f"### Question {i + 1}{mark}")
            parts.append(spec.text.strip())
            parts.append("Rubric / expectations:")
            for r in spec.rubric_items or []:
                parts.append(f"- {r}")
            if spec.hints:
                parts.append("Progressive hints:")
                for h in spec.hints:
                    parts.append(f"- {h}")
            parts.append("")
    parts.append("## Latest in-app feedback for the current question")
    parts.append(
        (runtime.feedback_md or "").strip()
        or "(None yet — student has not received capture feedback for this question.)"
    )
    parts.append("")
    parts.append("## Prior graded work (saved session files)")
    parts.append(
        study_answer.collect_graded_feedback_history(_study_paper_dir(runtime.session_id), n)
    )
    parts.append("")
    mode = _current_answer_mode(runtime)
    parts.append(f"## Current question answer mode: **{mode}**")
    if mode == "oral":
        oral_now, _ = _oral_transcript_for_runtime(runtime)
        parts.append("## Student's spoken answer for the current question (transcript)")
        parts.append(
            oral_now.strip()
            or "(Not recorded yet — student has not submitted a spoken answer for this question.)"
        )
    parts.append("")
    parts.append(
        study_answer.collect_oral_transcripts_for_ama(
            _study_paper_dir(runtime.session_id), n, runtime.current_index
        )
    )
    return "\n".join(parts)


def _format_ama_chat_for_prompt(turns: list[dict[str, str]]) -> str:
    if not turns:
        return ""
    lines: list[str] = ["## Tutor chat in this session (most recent last)"]
    for t in turns[-30:]:
        role = str(t.get("role", "user"))
        c = (t.get("content") or "").strip()
        who = "Student" if role == "user" else "Tutor"
        lines.append(f"**{who}:** {c}")
    out = "\n\n".join(lines)
    if len(out) > 12000:
        out = "…(earlier chat truncated)…\n\n" + out[-12000:]
    return out


app = FastAPI(title="Jetson Oral Exam Backend", version="0.1.0")

# Dev-friendly CORS so the Vite UI (localhost:5173) can call this service (localhost:8001).
# Tighten this list in production (e.g. to your Jetson-hosted student UI origin).
app.add_middleware(
    CORSMiddleware,
    # Study UI may be served from the Jetson LAN IP or another host; browser JPEG upload needs POST CORS.
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_lock = threading.Lock()
_exams: dict[str, _ExamRuntime] = {}
_study_runs: dict[str, _StudyRuntime] = {}


def _study_paper_dir(session_id: str) -> Path:
    """Resolve the ``paper/`` subfolder used for study artifacts + logs."""
    return settings.SESSIONS_DIR / session_id / "paper"

def _metrics_events_path(runtime: _StudyRuntime) -> Path | None:
    target_dir = _metrics_session_dir(runtime.session_id, runtime.student_id or "", runtime.day_run_id or "")
    if target_dir is None:
        return None
    return target_dir / "events.jsonl"


def _metrics_log(runtime: _StudyRuntime, event: dict[str, Any]) -> None:
    """
    Mirror key telemetry into a student/day-run metrics folder.
    Never raises.
    """
    try:
        path = _metrics_events_path(runtime)
        if path is None:
            return
        payload: dict[str, Any] = {
            "student_id": runtime.student_id,
            "day_run_id": runtime.day_run_id,
            "session_id": runtime.session_id,
            "question_index": runtime.current_index,
        }
        payload.update(event)
        metrics_log.log_event(path, payload)
    except Exception:
        return


def _metrics_log_from_context(session_id: str, event: dict[str, Any]) -> None:
    """
    Best-effort metrics log when the in-memory runtime is missing (e.g. after restart).
    Never raises.
    """
    try:
        ctx = _load_study_context(session_id)
        student_id = str(ctx.get("student_id") or "")
        day_run_id = str(ctx.get("day_run_id") or "")
        target_dir = _metrics_session_dir(session_id, student_id, day_run_id)
        if target_dir is None:
            return
        metrics_log.log_event(
            target_dir / "events.jsonl",
            {"session_id": session_id, "student_id": student_id, "day_run_id": day_run_id, **event},
        )
    except Exception:
        return


def _study_log_client_event(session_id: str, runtime: _StudyRuntime | None, event: dict[str, Any]) -> None:
    """
    Log a client-emitted telemetry event to both the paper session log and metrics mirror.
    Never raises.
    """
    try:
        paper_dir = _study_paper_dir(session_id)
        session_log.log_event(paper_dir, {"session_id": session_id, **event})
        if runtime is not None:
            _metrics_log(runtime, event)
        else:
            _metrics_log_from_context(session_id, event)
    except Exception:
        return


_STUDY_CAPTURE_LIMIT = 5


def _study_question_dir(runtime: _StudyRuntime) -> Path:
    return _study_paper_dir(runtime.session_id) / f"q{runtime.current_index}"


def _list_study_question_images(runtime: _StudyRuntime) -> list[Path]:
    q_dir = _study_question_dir(runtime)
    if not q_dir.is_dir():
        return []
    # Only consider JPEG files written by capture endpoints.
    images = sorted(q_dir.glob("paper_*.jpg"))
    return [p for p in images if p.is_file()]


def _update_study_latest_image(runtime: _StudyRuntime, img_path: Path) -> None:
    runtime.last_image_path = str(img_path)
    runtime.last_image_url = f"/jetson/study-guide/runs/{runtime.session_id}/latest-image?ts={int(time.time())}"


def _study_context_path(session_id: str) -> Path:
    return _study_paper_dir(session_id) / "metrics_context.json"


def _persist_study_context(runtime: _StudyRuntime) -> None:
    payload = {
        "session_id": runtime.session_id,
        "student_id": runtime.student_id,
        "day_run_id": runtime.day_run_id,
        "study_plan": dict(runtime.study_plan or {}),
        "question_specs": [
            {
                "qid": s.qid,
                "question": s.text,
                "rubric_items": list(s.rubric_items or []),
                "difficulty": s.difficulty or "",
                "hints": list(s.hints or []),
            }
            for s in (runtime.question_specs or [])
        ],
    }
    try:
        path = _study_context_path(runtime.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(__import__("json").dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass


def _load_study_context(session_id: str) -> dict[str, Any]:
    path = _study_context_path(session_id)
    if not path.is_file():
        return {}
    try:
        return __import__("json").loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _metrics_session_dir(session_id: str, student_id: str, day_run_id: str) -> Path | None:
    sid = (student_id or "").strip()
    did = (day_run_id or "").strip()
    if not sid or not did:
        return None
    return settings.BASE_DIR / "metrics" / "students" / sid / "day_runs" / did / "sessions" / session_id


def _session_from_runtime_or_context(runtime: _StudyRuntime | None, session_id: str) -> tuple[str, str]:
    if runtime is not None:
        return runtime.student_id or "", runtime.day_run_id or ""
    ctx = _load_study_context(session_id)
    return str(ctx.get("student_id") or ""), str(ctx.get("day_run_id") or "")


def _write_metrics_artifacts(session_id: str, runtime: _StudyRuntime | None = None) -> None:
    import json as _json

    student_id, day_run_id = _session_from_runtime_or_context(runtime, session_id)
    target_dir = _metrics_session_dir(session_id, student_id, day_run_id)
    if target_dir is None:
        return
    target_dir.mkdir(parents=True, exist_ok=True)

    paper_dir = _study_paper_dir(session_id)
    metrics_events_path = target_dir / "events.jsonl"
    events = metrics_log.read_events(metrics_events_path)
    context = _load_study_context(session_id)

    interactions = session_log.read_events(paper_dir)
    survey = None
    survey_path = paper_dir / "survey.json"
    if survey_path.is_file():
        try:
            survey = _json.loads(survey_path.read_text(encoding="utf-8"))
        except Exception:
            survey = None
    study_feedback = None
    study_feedback_path = paper_dir / "study_feedback.json"
    if study_feedback_path.is_file():
        try:
            study_feedback = _json.loads(study_feedback_path.read_text(encoding="utf-8"))
        except Exception:
            study_feedback = None

    question_specs = context.get("question_specs") or []
    captures_by_question: list[dict[str, Any]] = []
    oral_by_question: list[dict[str, Any]] = []
    ama_transcript: list[dict[str, Any]] = []
    for event in interactions:
        if event.get("type") == "ama_turn":
            ama_transcript.append(
                {
                    "ts": event.get("ts"),
                    "question_index": event.get("question_index"),
                    "role": event.get("role"),
                    "content": event.get("content"),
                    "model": event.get("model"),
                }
            )
    for q_dir in sorted([p for p in paper_dir.glob("q*") if p.is_dir()]):
        try:
            qi = int(q_dir.name[1:])
        except Exception:
            qi = -1
        images = [str(p) for p in sorted(q_dir.glob("paper_*.jpg")) if p.is_file()]
        feedback_json = None
        feedback_md = None
        if (q_dir / "paper_feedback.json").is_file():
            feedback_json = str(q_dir / "paper_feedback.json")
        if (q_dir / "paper_feedback.md").is_file():
            feedback_md = str(q_dir / "paper_feedback.md")
        mode = study_answer.get_answer_mode(paper_dir, qi) if qi >= 0 else "paper"
        captures_by_question.append(
            {
                "question_index": qi,
                "answer_mode": mode,
                "question": question_specs[qi]["question"] if 0 <= qi < len(question_specs) else None,
                "difficulty": question_specs[qi].get("difficulty", "") if 0 <= qi < len(question_specs) else "",
                "images": images,
                "image_count": len(images),
                "feedback_json_path": feedback_json,
                "feedback_md_path": feedback_md,
            }
        )
        oral_text, oral_meta = study_answer.load_oral_transcript(paper_dir, qi) if qi >= 0 else ("", {})
        oral_fb_json = q_dir / "oral_feedback.json"
        oral_fb_md = study_answer.oral_feedback_md_path(paper_dir, qi)
        if oral_text.strip() or oral_meta or oral_fb_json.is_file():
            oral_by_question.append(
                {
                    "question_index": qi,
                    "answer_mode": mode,
                    "transcript": oral_text,
                    "transcript_char_count": len(oral_text),
                    "transcript_word_count": len(oral_text.split()) if oral_text else 0,
                    "audio_filename": oral_meta.get("audio_filename"),
                    "oral_feedback_json_path": str(oral_fb_json) if oral_fb_json.is_file() else None,
                    "oral_feedback_md_path": str(oral_fb_md) if oral_fb_md.is_file() else None,
                }
            )

    snapshot = {
        "session_id": session_id,
        "student_id": student_id,
        "day_run_id": day_run_id,
        "study_plan": context.get("study_plan") or {},
        "question_specs": question_specs,
        "captures_by_question": captures_by_question,
        "oral_by_question": oral_by_question,
        "answer_modes": study_answer.load_answer_modes(paper_dir),
        "ama_transcript": ama_transcript,
        "study_feedback": study_feedback,
        "survey": survey,
        "paper_dir": str(paper_dir),
        "interactions_path": str(paper_dir / "interactions.jsonl"),
    }
    (target_dir / "session_snapshot.json").write_text(
        _json.dumps(snapshot, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    if survey is not None:
        (target_dir / "survey_answers.json").write_text(
            _json.dumps(survey, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
    metrics_log.write_summary(
        metrics_events_path,
        summary=build_metrics_summary(session_id, events, sessions_root=settings.SESSIONS_DIR),
    )


def _study_log(runtime: _StudyRuntime, event: dict[str, Any]) -> None:
    """
    Thin seam around :func:`session_log.log_event` that injects the current
    question index and session id. Never raises - callers treat it as pure
    telemetry so a disk hiccup cannot break grading or the HTTP response.
    """
    try:
        payload: dict[str, Any] = {
            "session_id": runtime.session_id,
            "question_index": runtime.current_index,
        }
        payload.update(event)
        session_log.log_event(_study_paper_dir(runtime.session_id), payload)
        _metrics_log(runtime, event)
    except Exception:
        # log_event already swallows I/O errors; this outer guard is for any
        # attribute errors on runtime itself.
        pass


def _speak_study_instructions() -> None:
    if not getattr(settings, "STUDY_GUIDE_SPEAK_INSTRUCTIONS", True):
        return
    text = getattr(settings, "STUDY_GUIDE_INSTRUCTIONS", "") or ""
    if not text.strip():
        return
    try:
        get_tts_client().speak(text)
    except Exception:
        # TTS is additive; study mode should still work without audio.
        pass


def _load_exam_config(path: Optional[str]) -> dict:
    import json

    if path:
        cfg_path = Path(path)
    else:
        cfg_path = settings.EXAMS_DIR / "example_exam.json"
    if not cfg_path.exists():
        raise FileNotFoundError(f"Exam config not found at {cfg_path}")
    return json.loads(cfg_path.read_text(encoding="utf-8"))

def _study_question_from_payload(payload: CreateStudyRunRequest) -> tuple[str, list[str]]:
    if payload.question_text and payload.rubric_items:
        return str(payload.question_text), list(payload.rubric_items)
    if payload.exam_config:
        questions = payload.exam_config.get("questions") or []
        if not questions:
            raise ValueError("exam_config has no questions")
        q0 = questions[0] or {}
        q_text = str(q0.get("text") or "")
        rubric = q0.get("rubric_items") or []
        if not q_text:
            raise ValueError("exam_config.questions[0].text is empty")
        if not isinstance(rubric, list) or not all(isinstance(x, str) for x in rubric):
            raise ValueError("exam_config.questions[0].rubric_items must be a list of strings")
        return q_text, list(rubric)
    raise ValueError("Provide either (question_text + rubric_items) or exam_config")


def _resolve_study_question_specs(payload: CreateStudyRunRequest) -> list[_StudyQuestionSpec]:
    if payload.practice_questions:
        specs: list[_StudyQuestionSpec] = []
        for p in payload.practice_questions:
            t = (p.text or "").strip()
            rub = [str(x) for x in (p.rubric_items or []) if str(x).strip()]
            hints = [str(x).strip() for x in (p.hints or []) if str(x).strip()]
            if not t or not rub:
                raise ValueError("Each practice_questions entry needs non-empty text and rubric_items")
            specs.append(
                _StudyQuestionSpec(
                    qid=(p.id or "").strip(),
                    text=t,
                    rubric_items=rub,
                    difficulty=(p.difficulty or "").strip(),
                    hints=hints,
                )
            )
        return specs
    q_text, rubric = _study_question_from_payload(payload)
    return [_StudyQuestionSpec(qid="", text=q_text, rubric_items=list(rubric))]


def _run_exam(runtime: _ExamRuntime, exam_config: dict) -> None:
    runtime.status = "speaking"
    runtime.started_at = datetime.utcnow()
    try:
        exam_config = dict(exam_config)
        exam_config["exam_id"] = runtime.session_id
        # Expose the first question text to the UI as soon as the exam starts.
        questions = exam_config.get("questions") or []
        if questions:
            runtime.current_question = questions[0].get("text", "") or ""
        exam_data = runtime.proctor.conduct_exam(exam_config)
        if exam_data.get("questions"):
            last_q = exam_data["questions"][-1]
            runtime.current_question = last_q.get("question", "")
            runtime.transcript_preview = (last_q.get("responses", [{}])[0].get("text") or "")[:200]
        # Notify central backend about artifacts if configured
        _notify_central_artifacts(runtime)
    finally:
        runtime.status = "done"
        runtime.finished_at = datetime.utcnow()
        runtime.proctor.shutdown()


def _central_base_url() -> Optional[str]:
    return os.environ.get("CENTRAL_API_BASE_URL")


def _post_central(path: str, payload: dict) -> Optional[dict]:
    base = _central_base_url()
    if not base:
        return None
    url = base.rstrip("/") + path
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
    except Exception:
        # For Jetson robustness we log to stdout only; central integration is additive.
        print(f"[jetson_backend] Failed to POST to central {url}")
    return None


def _notify_central_artifacts(runtime: _ExamRuntime) -> None:
    """
    After an exam completes, notify central backend about where artifacts live.

    This uses the same session_id for both Jetson and central for MVP.
    """
    base = _central_base_url()
    if not base:
        return
    session_id = runtime.central_session_id or runtime.session_id
    session_dir = settings.SESSIONS_DIR / runtime.session_id
    artifacts = {
        "session_dir_uri": str(session_dir),
        "recording_uri": str(session_dir / "recording.mp4"),
        "final_transcript_uri": str(session_dir / "final_transcript.json"),
    }
    _post_central(f"/sessions/{session_id}/artifacts", {"artifacts": artifacts})


@app.post("/jetson/exams", response_model=CreateExamResponse)
def create_exam(payload: CreateExamRequest) -> CreateExamResponse:
    with _lock:
        if payload.session_id in _exams:
            raise HTTPException(status_code=400, detail="Exam already running for this session")
        # When running under the Jetson HTTP backend, we disable keyboard-driven
        # "press Enter" control so that the exam flow is controlled entirely by
        # the web UI via /jetson/exams/{session_id}/done.
        proctor = OralExamProctor(enable_keyboard_done=False)
        runtime = _ExamRuntime(session_id=payload.session_id, proctor=proctor, thread=None)  # type: ignore[arg-type]
        runtime.central_session_id = payload.session_id
        _exams[payload.session_id] = runtime

    if payload.exam_config is not None:
        exam_config = payload.exam_config
    else:
        try:
            exam_config = _load_exam_config(payload.exam_config_path)
        except FileNotFoundError as e:
            with _lock:
                _exams.pop(payload.session_id, None)
            raise HTTPException(status_code=400, detail=str(e))

    t = threading.Thread(target=_run_exam, args=(runtime, exam_config), daemon=True)
    runtime.thread = t
    t.start()
    return CreateExamResponse(session_id=payload.session_id)

def _study_process_saved_image(runtime: _StudyRuntime, img_path: Path) -> None:
    """Run vision + LLM grading on a JPEG already on disk."""
    _update_study_latest_image(runtime, img_path)
    runtime.status = "thinking"
    try:
        fb = request_paper_feedback(
            question_text=runtime.question_text,
            rubric_items=runtime.rubric_items or [],
            image_paths=[img_path],
        )
        runtime.feedback_md = fb.md
        runtime.feedback_json = fb.json
        session_dir = img_path.parent
        (session_dir / "paper_feedback.json").write_text(
            __import__("json").dumps(fb.json, indent=2), encoding="utf-8"
        )
        (session_dir / "paper_feedback.md").write_text(fb.md + "\n", encoding="utf-8")
        _study_log(
            runtime,
            {
                "type": "capture_feedback",
                "image_filename": img_path.name,
                "image_path": str(img_path),
                "feedback_json": fb.json,
                "feedback_md": fb.md,
            },
        )
        runtime.status = "done"
        runtime.finished_at = datetime.utcnow()
    except Exception as e:
        _study_log(
            runtime,
            {
                "type": "capture_feedback_error",
                "image_filename": img_path.name,
                "image_path": str(img_path),
                "error": str(e),
            },
        )
        runtime.status = "error"
        runtime.error = str(e)
        runtime.finished_at = datetime.utcnow()


def _study_process_saved_images(runtime: _StudyRuntime, img_paths: list[Path]) -> None:
    """Grade multiple captured pages as one response (used when student submits multi-page work)."""
    if not img_paths:
        runtime.status = "error"
        runtime.error = "No captured images to grade."
        runtime.finished_at = datetime.utcnow()
        return
    _update_study_latest_image(runtime, img_paths[-1])
    runtime.status = "thinking"
    t0 = time.time()
    _study_log(
        runtime,
        {
            "type": "grade_requested",
            "source": "paper",
            "answer_mode": "paper",
            "image_count": len(img_paths),
            "image_filenames": [p.name for p in img_paths],
        },
    )
    try:
        fb = request_paper_feedback(
            question_text=runtime.question_text,
            rubric_items=runtime.rubric_items or [],
            image_paths=img_paths,
        )
        dt_ms = int((time.time() - t0) * 1000)
        runtime.feedback_md = fb.md
        runtime.feedback_json = fb.json
        session_dir = img_paths[-1].parent
        (session_dir / "paper_feedback.json").write_text(
            __import__("json").dumps(fb.json, indent=2), encoding="utf-8"
        )
        (session_dir / "paper_feedback.md").write_text(fb.md + "\n", encoding="utf-8")
        _study_log(
            runtime,
            {
                "type": "capture_feedback",
                "source": "multi",
                "image_count": len(img_paths),
                "image_filenames": [p.name for p in img_paths],
                "image_paths": [str(p) for p in img_paths],
                "feedback_json": fb.json,
                "feedback_md": fb.md,
                "grade_duration_ms": dt_ms,
            },
        )
        _study_log(
            runtime,
            {
                "type": "grade_completed",
                "ok": True,
                "duration_ms": dt_ms,
                "source": "paper",
                "answer_mode": "paper",
            },
        )
        runtime.status = "done"
        runtime.finished_at = datetime.utcnow()
    except Exception as e:
        dt_ms = int((time.time() - t0) * 1000)
        _study_log(
            runtime,
            {
                "type": "capture_feedback_error",
                "source": "multi",
                "image_count": len(img_paths),
                "image_filenames": [p.name for p in img_paths],
                "image_paths": [str(p) for p in img_paths],
                "error": str(e),
                "grade_duration_ms": dt_ms,
            },
        )
        _study_log(
            runtime,
            {
                "type": "grade_completed",
                "ok": False,
                "duration_ms": dt_ms,
                "error": str(e),
                "source": "paper",
                "answer_mode": "paper",
            },
        )
        runtime.status = "error"
        runtime.error = str(e)
        runtime.finished_at = datetime.utcnow()


def _run_study_capture(runtime: _StudyRuntime, *, width: int, height: int) -> None:
    runtime.status = "capturing"
    runtime.started_at = datetime.utcnow()
    try:
        paper_root = settings.SESSIONS_DIR / runtime.session_id / "paper"
        paper_root.mkdir(parents=True, exist_ok=True)
        # Per-question subfolder so multi-question runs aggregate cleanly (q0, q1, …).
        q_dir = paper_root / f"q{runtime.current_index}"
        q_dir.mkdir(parents=True, exist_ok=True)
        existing = list(q_dir.glob("paper_*.jpg"))
        if len(existing) >= _STUDY_CAPTURE_LIMIT:
            runtime.status = "error"
            runtime.error = f"Capture limit reached ({_STUDY_CAPTURE_LIMIT})."
            runtime.finished_at = datetime.utcnow()
            return
        img_path = q_dir / f"paper_{int(time.time())}.jpg"
        captured = capture_paper_image(
            camera_device=settings.CAMERA_DEVICE,
            output_path=img_path,
            width=width,
            height=height,
        )
        _study_log(
            runtime,
            {
                "type": "capture",
                "source": "camera",
                "image_path": str(captured),
                "image_filename": Path(captured).name,
            },
        )
        _update_study_latest_image(runtime, Path(captured))
        runtime.status = "idle"
        runtime.finished_at = datetime.utcnow()
    except Exception as e:
        _study_log(runtime, {"type": "capture_failed", "error": str(e)})
        runtime.status = "error"
        runtime.error = str(e)
        runtime.finished_at = datetime.utcnow()


def _run_study_grade_upload(runtime: _StudyRuntime, img_path: Path) -> None:
    """Background: grade captured pages (camera stays open in Firefox)."""
    runtime.started_at = datetime.utcnow()
    _study_process_saved_images(runtime, _list_study_question_images(runtime))


def _transcribe_study_audio_file(audio_path: Path) -> dict:
    from stt.stt_service import get_stt_service

    stt = get_stt_service()
    prompt = getattr(settings, "STUDY_STT_INITIAL_PROMPT", None) or settings.STT_INITIAL_PROMPT
    return stt.transcribe(str(audio_path), initial_prompt=prompt)


def _run_oral_upload(runtime: _StudyRuntime, audio_path: Path, *, audio_bytes: int = 0) -> None:
    """Background: STT a browser-uploaded audio answer for the current question."""
    runtime.status = "thinking"
    runtime.started_at = datetime.utcnow()
    paper_root = _study_paper_dir(runtime.session_id)
    t_pipeline = time.time()
    try:
        if not audio_bytes and audio_path.is_file():
            audio_bytes = audio_path.stat().st_size
        _study_log(
            runtime,
            {
                "type": "oral_upload_started",
                "audio_filename": audio_path.name,
                "audio_bytes": audio_bytes,
            },
        )
        t_stt = time.time()
        result = _transcribe_study_audio_file(audio_path)
        stt_sec = float(result.get("transcription_time") or 0)
        transcription_duration_ms = int(stt_sec * 1000) if stt_sec > 0 else int((time.time() - t_stt) * 1000)
        text = (result.get("text") or "").strip()
        if not text:
            raise ValueError("No speech detected. Try speaking closer to the microphone and record again.")
        study_answer.save_oral_transcript(
            paper_root,
            runtime.current_index,
            text=text,
            segments=result.get("segments") or [],
            audio_filename=audio_path.name,
        )
        upload_to_transcript_ms = int((time.time() - t_pipeline) * 1000)
        _study_log(
            runtime,
            {
                "type": "oral_transcript",
                "audio_filename": audio_path.name,
                "audio_bytes": audio_bytes,
                "transcript": text,
                "transcript_char_count": len(text),
                "transcript_word_count": len(text.split()),
                "transcription_time_sec": stt_sec,
                "transcription_duration_ms": transcription_duration_ms,
                "upload_to_transcript_ms": upload_to_transcript_ms,
            },
        )
        runtime.status = "idle"
        runtime.error = ""
        runtime.finished_at = datetime.utcnow()
    except Exception as e:
        _study_log(runtime, {"type": "oral_transcript_error", "error": str(e)})
        runtime.status = "error"
        runtime.error = str(e)
        runtime.finished_at = datetime.utcnow()


def _study_process_oral_transcript(runtime: _StudyRuntime) -> None:
    """Grade the current question from a spoken transcript."""
    transcript, ok = _oral_transcript_for_runtime(runtime)
    if not ok:
        runtime.status = "error"
        runtime.error = "Record your spoken answer before evaluating."
        runtime.finished_at = datetime.utcnow()
        return
    runtime.status = "thinking"
    t0 = time.time()
    paper_root = _study_paper_dir(runtime.session_id)
    q_dir = study_answer.question_dir(paper_root, runtime.current_index)
    _study_log(
        runtime,
        {
            "type": "grade_requested",
            "source": "oral",
            "answer_mode": "oral",
            "transcript_length": len(transcript),
            "transcript_char_count": len(transcript),
            "transcript_word_count": len(transcript.split()),
        },
    )
    try:
        fb = request_oral_feedback(
            question_text=runtime.question_text,
            rubric_items=runtime.rubric_items or [],
            transcript=transcript,
        )
        dt_ms = int((time.time() - t0) * 1000)
        runtime.feedback_md = fb.md
        runtime.feedback_json = fb.json
        q_dir.mkdir(parents=True, exist_ok=True)
        (q_dir / "oral_feedback.json").write_text(
            __import__("json").dumps(fb.json, indent=2), encoding="utf-8"
        )
        study_answer.oral_feedback_md_path(paper_root, runtime.current_index).write_text(
            fb.md + "\n", encoding="utf-8"
        )
        _study_log(
            runtime,
            {
                "type": "oral_feedback",
                "source": "oral",
                "answer_mode": "oral",
                "transcript": transcript,
                "feedback_json": fb.json,
                "feedback_md": fb.md,
                "grade_duration_ms": dt_ms,
            },
        )
        _study_log(
            runtime,
            {
                "type": "grade_completed",
                "ok": True,
                "duration_ms": dt_ms,
                "source": "oral",
                "answer_mode": "oral",
            },
        )
        runtime.status = "done"
        runtime.finished_at = datetime.utcnow()
    except Exception as e:
        dt_ms = int((time.time() - t0) * 1000)
        _study_log(
            runtime,
            {"type": "oral_feedback_error", "error": str(e), "grade_duration_ms": dt_ms},
        )
        _study_log(
            runtime,
            {"type": "grade_completed", "ok": False, "duration_ms": dt_ms, "error": str(e), "source": "oral"},
        )
        runtime.status = "error"
        runtime.error = str(e)
        runtime.finished_at = datetime.utcnow()


def _run_study_grade(runtime: _StudyRuntime) -> None:
    """Background: grade paper captures or oral transcript depending on answer mode."""
    runtime.started_at = datetime.utcnow()
    if _current_answer_mode(runtime) == "oral":
        _study_process_oral_transcript(runtime)
    else:
        _study_process_saved_images(runtime, _list_study_question_images(runtime))


@app.post("/jetson/study-guide/runs", response_model=CreateStudyRunResponse)
def create_study_run(payload: CreateStudyRunRequest) -> CreateStudyRunResponse:
    try:
        specs = _resolve_study_question_specs(payload)
    except Exception as e:
        # FastAPI access logs don't include response bodies; emit a compact
        # server-side hint so debugging 400s is quick on Jetson.
        try:
            has_exam = payload.exam_config is not None
            q_len = len((payload.exam_config or {}).get("questions") or []) if has_exam else 0
            pq_len = len(payload.practice_questions or [])
            print(
                "[jetson_backend] create_study_run 400:",
                str(e),
                f"(session_id={payload.session_id}, student_id={payload.student_id}, day_run_id={payload.day_run_id}, "
                f"has_exam_config={has_exam}, exam_questions={q_len}, practice_questions={pq_len})",
            )
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=str(e))
    if not specs:
        raise HTTPException(status_code=400, detail="No study questions resolved")
    first = specs[0]

    with _lock:
        if payload.session_id in _study_runs:
            raise HTTPException(status_code=400, detail="Study run already exists for this session")
        student_id = (payload.student_id or "").strip()
        day_run_id = (payload.day_run_id or "").strip()
        runtime = _StudyRuntime(
            session_id=payload.session_id,
            student_id=student_id,
            day_run_id=day_run_id,
            study_plan=dict(payload.study_plan or {}),
            status="idle",
            question_text=first.text,
            rubric_items=first.rubric_items,
            hints=list(first.hints or []),
            question_specs=list(specs),
            current_index=0,
        )
        _study_runs[payload.session_id] = runtime
    _persist_study_context(runtime)

    _study_log(
        runtime,
        {
            "type": "run_started",
            "student_id": runtime.student_id or None,
            "day_run_id": runtime.day_run_id or None,
            "study_plan": dict(runtime.study_plan or {}),
            "question_specs": [
                {
                    "qid": s.qid,
                    "question": s.text,
                    "rubric_items": list(s.rubric_items or []),
                    "difficulty": s.difficulty or "",
                    "hints": list(s.hints or []),
                }
                for s in specs
            ],
        },
    )
    _study_log(
        runtime,
        {
            "type": "question_shown",
            "question": first.text,
            "rubric_items": list(first.rubric_items or []),
            "hints": list(first.hints or []),
        },
    )

    # Speak instructions asynchronously so the HTTP request returns quickly.
    threading.Thread(target=_speak_study_instructions, daemon=True).start()
    return CreateStudyRunResponse(session_id=payload.session_id)


@app.get("/jetson/study-guide/runs/{session_id}/state", response_model=StudyRunState)
def get_study_state(session_id: str) -> StudyRunState:
    with _lock:
        runtime = _study_runs.get(session_id)
    if not runtime:
        raise HTTPException(status_code=404, detail="Study run not found")
    n = len(runtime.question_specs) if runtime.question_specs else 1
    idx = runtime.current_index if runtime.question_specs else 0
    captures = _list_study_question_images(runtime)
    oral_text, oral_ok = _oral_transcript_for_runtime(runtime)
    return StudyRunState(
        session_id=session_id,
        status=runtime.status,
        questionText=runtime.question_text or "",
        feedbackMarkdown=runtime.feedback_md or "",
        followUpMarkdown=runtime.followup_md or "",
        latestImageUrl=runtime.last_image_url or "",
        error=runtime.error or "",
        captureCount=len(captures),
        captureLimit=_STUDY_CAPTURE_LIMIT,
        questionIndex=min(idx + 1, n),
        questionCount=max(n, 1),
        hints=list(runtime.hints or []),
        ama_turns=[
            AmaTurnModel(role=str(t.get("role", "user")), content=str(t.get("content", "")))
            for t in runtime.ama_turns
        ],
        answerMode=_current_answer_mode(runtime),
        oralTranscript=oral_text,
        oralHasRecording=oral_ok,
    )


@app.get("/jetson/study-guide/runs/{session_id}/latest-image")
def get_latest_study_image(session_id: str):
    with _lock:
        runtime = _study_runs.get(session_id)
    if not runtime:
        raise HTTPException(status_code=404, detail="Study run not found")
    if not runtime.last_image_path:
        raise HTTPException(status_code=404, detail="No image captured yet")
    path = Path(runtime.last_image_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file missing on disk")
    return FileResponse(str(path), media_type="image/jpeg")


@app.post("/jetson/study-guide/runs/{session_id}/answer-mode")
def set_study_answer_mode(session_id: str, payload: SetAnswerModeRequest) -> dict:
    """Choose paper (camera) or oral (microphone) for the current question."""
    with _lock:
        runtime = _study_runs.get(session_id)
        if not runtime:
            raise HTTPException(status_code=404, detail="Study run not found")
        if runtime.thread is not None and runtime.thread.is_alive():
            raise HTTPException(status_code=400, detail="Wait for the current operation to finish.")
        captures = _list_study_question_images(runtime)
        oral_text, _ = _oral_transcript_for_runtime(runtime)
        if captures or oral_text.strip() or (runtime.feedback_md or "").strip():
            raise HTTPException(
                status_code=400,
                detail="Cannot switch answer mode after you have started this question. Go to the next question or retake.",
            )
        study_answer.save_answer_mode(
            _study_paper_dir(session_id), runtime.current_index, payload.mode
        )
        _study_log(
            runtime,
            {"type": "answer_mode_set", "mode": payload.mode},
        )
    return {"status": "ok", "answerMode": payload.mode}


@app.post("/jetson/study-guide/runs/{session_id}/capture")
def capture_and_grade(session_id: str, payload: CaptureRequest) -> dict:
    with _lock:
        runtime = _study_runs.get(session_id)
        if not runtime:
            raise HTTPException(status_code=404, detail="Study run not found")
        if _current_answer_mode(runtime) == "oral":
            raise HTTPException(
                status_code=400,
                detail="This question uses spoken answers. Use the microphone to record your answer.",
            )
        if runtime.thread is not None and runtime.thread.is_alive():
            raise HTTPException(status_code=400, detail="Capture already running")
        if len(_list_study_question_images(runtime)) >= _STUDY_CAPTURE_LIMIT:
            raise HTTPException(status_code=400, detail=f"Capture limit reached ({_STUDY_CAPTURE_LIMIT}).")
        t = threading.Thread(
            target=_run_study_capture,
            args=(runtime,),
            kwargs={"width": int(payload.width), "height": int(payload.height)},
            daemon=True,
        )
        runtime.thread = t
        t.start()
    return {"status": "started"}


@app.post("/jetson/study-guide/runs/{session_id}/grade")
def grade_captures(session_id: str, payload: GradeRequest) -> dict:  # noqa: ARG001
    """
    Grade the current question: paper captures (camera) or spoken transcript (microphone),
    depending on the student's chosen answer mode for this question.
    """
    with _lock:
        runtime = _study_runs.get(session_id)
        if not runtime:
            raise HTTPException(status_code=404, detail="Study run not found")
        if runtime.thread is not None and runtime.thread.is_alive():
            raise HTTPException(status_code=400, detail="Grading already running")
        mode = _current_answer_mode(runtime)
        if mode == "oral":
            oral_text, oral_ok = _oral_transcript_for_runtime(runtime)
            if not oral_ok:
                raise HTTPException(
                    status_code=400,
                    detail="Record your spoken answer before evaluating.",
                )
        else:
            captures = _list_study_question_images(runtime)
            if not captures:
                raise HTTPException(status_code=400, detail="Capture at least one photo before grading.")
        t = threading.Thread(target=_run_study_grade, args=(runtime,), daemon=True)
        runtime.thread = t
        t.start()
        capture_count = len(_list_study_question_images(runtime))
    return {
        "status": "started",
        "captureCount": capture_count,
        "captureLimit": _STUDY_CAPTURE_LIMIT,
        "answerMode": mode,
    }


@app.post("/jetson/study-guide/runs/{session_id}/next-question")
def study_next_question(session_id: str) -> dict:
    """Advance to the next practice question (question-bank multi-question runs)."""
    with _lock:
        runtime = _study_runs.get(session_id)
        if not runtime:
            raise HTTPException(status_code=404, detail="Study run not found")
        if runtime.thread is not None and runtime.thread.is_alive():
            raise HTTPException(status_code=400, detail="Capture still running")
        specs = runtime.question_specs or []
        if len(specs) <= 1:
            raise HTTPException(status_code=400, detail="No next question in this run")
        if runtime.current_index >= len(specs) - 1:
            raise HTTPException(status_code=400, detail="Already on the last question")
        nxt = runtime.current_index + 1
        n_spec = specs[nxt]
        runtime.current_index = nxt
        runtime.question_text = n_spec.text
        runtime.rubric_items = list(n_spec.rubric_items)
        runtime.hints = list(n_spec.hints or [])
        runtime.feedback_md = ""
        runtime.feedback_json = None
        runtime.followup_md = ""
        runtime.error = ""
        runtime.status = "idle"
        # New question has no capture yet — hide previous question’s preview in the UI.
        runtime.last_image_path = ""
        runtime.last_image_url = ""

    _study_log(
        runtime,
        {
            "type": "question_shown",
            "question": n_spec.text,
            "rubric_items": list(n_spec.rubric_items or []),
            "hints": list(n_spec.hints or []),
        },
    )
    return {"status": "ok", "questionIndex": nxt + 1, "questionCount": len(specs)}


_MAX_STUDY_UPLOAD_BYTES = 15 * 1024 * 1024


@app.post("/jetson/study-guide/runs/{session_id}/capture-upload")
async def capture_upload(session_id: str, image: UploadFile = File(...)) -> dict:
    """
    Accept a JPEG from the browser (same frame as the live preview).

    Avoids opening /dev/video0 on the server while Firefox is using the camera.
    """
    with _lock:
        runtime = _study_runs.get(session_id)
        if not runtime:
            raise HTTPException(status_code=404, detail="Study run not found")
        if _current_answer_mode(runtime) == "oral":
            raise HTTPException(
                status_code=400,
                detail="This question uses spoken answers. Use the microphone to record your answer.",
            )
    raw = await image.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty image")
    if len(raw) > _MAX_STUDY_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image too large")
    if not raw.startswith(b"\xff\xd8"):
        raise HTTPException(status_code=400, detail="Expected a JPEG image")

    paper_root = settings.SESSIONS_DIR / session_id / "paper"
    paper_root.mkdir(parents=True, exist_ok=True)

    with _lock:
        runtime = _study_runs.get(session_id)
        if not runtime:
            raise HTTPException(status_code=404, detail="Study run not found")
        if runtime.thread is not None and runtime.thread.is_alive():
            raise HTTPException(status_code=400, detail="Capture already running")
        q_dir = paper_root / f"q{runtime.current_index}"
        q_dir.mkdir(parents=True, exist_ok=True)
        existing = [p for p in q_dir.glob("paper_*.jpg") if p.is_file()]
        if len(existing) >= _STUDY_CAPTURE_LIMIT:
            raise HTTPException(status_code=400, detail=f"Capture limit reached ({_STUDY_CAPTURE_LIMIT}).")
        img_path = q_dir / f"paper_{time.time_ns()}.jpg"
        try:
            img_path.write_bytes(raw)
        except Exception as e:
            _study_log(runtime, {"type": "capture_failed", "source": "upload", "error": str(e)})
            raise
        _study_log(
            runtime,
            {
                "type": "capture",
                "source": "upload",
                "image_path": str(img_path),
                "image_filename": img_path.name,
                "bytes": len(raw),
            },
        )
        _update_study_latest_image(runtime, img_path)

    # Capture only (no grading) — the student may capture multiple pages first.
    return {"status": "captured", "captureCount": len(existing) + 1, "captureLimit": _STUDY_CAPTURE_LIMIT}


@app.post("/jetson/study-guide/runs/{session_id}/retake-last")
def retake_last_capture(session_id: str) -> dict:
    """
    Delete the most recent captured JPEG for the current question.

    This supports a "Retake" button in the web UI when a student captures a blurry
    or off-frame photo. The student can then capture again without burning one
    of the limited capture slots.
    """
    with _lock:
        runtime = _study_runs.get(session_id)
        if not runtime:
            raise HTTPException(status_code=404, detail="Study run not found")
        if runtime.thread is not None and runtime.thread.is_alive():
            raise HTTPException(status_code=400, detail="Capture still running")

        images = _list_study_question_images(runtime)
        if not images:
            raise HTTPException(status_code=400, detail="No captured photo to retake")

        last = images[-1]
        try:
            last.unlink(missing_ok=True)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete photo: {e}") from e

        remaining = _list_study_question_images(runtime)
        if remaining:
            _update_study_latest_image(runtime, remaining[-1])
        else:
            runtime.last_image_path = ""
            runtime.last_image_url = ""

        runtime.feedback_md = ""
        runtime.feedback_json = None
        runtime.followup_md = ""
        runtime.error = ""
        runtime.status = "idle"

        _study_log(
            runtime,
            {
                "type": "retake_last",
                "deleted_image_path": str(last),
                "deleted_image_filename": last.name,
                "remaining_count": len(remaining),
            },
        )

    return {"status": "ok", "captureCount": len(remaining), "captureLimit": _STUDY_CAPTURE_LIMIT}


_MAX_ORAL_UPLOAD_BYTES = 25 * 1024 * 1024
_ORAL_EXT_BY_MIME = {
    "audio/webm": ".webm",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "video/webm": ".webm",
}


@app.post("/jetson/study-guide/runs/{session_id}/oral-upload")
async def oral_upload(session_id: str, audio: UploadFile = File(...)) -> dict:
    """
    Accept a spoken answer from the browser microphone; transcribe with faster-whisper on Jetson.
    """
    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty audio")
    if len(raw) > _MAX_ORAL_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Audio too large")

    content_type = (audio.content_type or "").split(";")[0].strip().lower()
    ext = _ORAL_EXT_BY_MIME.get(content_type, ".webm")

    with _lock:
        runtime = _study_runs.get(session_id)
        if not runtime:
            raise HTTPException(status_code=404, detail="Study run not found")
        if _current_answer_mode(runtime) != "oral":
            raise HTTPException(
                status_code=400,
                detail="This question uses paper answers. Switch to “Write on paper” or choose Speak for this question.",
            )
        if runtime.thread is not None and runtime.thread.is_alive():
            raise HTTPException(status_code=400, detail="Transcription already running")

        paper_root = _study_paper_dir(session_id)
        q_dir = study_answer.question_dir(paper_root, runtime.current_index)
        q_dir.mkdir(parents=True, exist_ok=True)
        study_answer.clear_oral_artifacts(paper_root, runtime.current_index)
        audio_path = q_dir / f"oral_upload{ext}"
        try:
            audio_path.write_bytes(raw)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save audio: {e}") from e

        runtime.feedback_md = ""
        runtime.feedback_json = None
        runtime.followup_md = ""
        runtime.error = ""

        t = threading.Thread(
            target=_run_oral_upload,
            args=(runtime, audio_path),
            kwargs={"audio_bytes": len(raw)},
            daemon=True,
        )
        runtime.thread = t
        t.start()

    return {"status": "started"}


@app.post("/jetson/study-guide/runs/{session_id}/retake-oral")
def retake_oral_answer(session_id: str) -> dict:
    """Clear the spoken recording/transcript for the current question so the student can re-record."""
    with _lock:
        runtime = _study_runs.get(session_id)
        if not runtime:
            raise HTTPException(status_code=404, detail="Study run not found")
        if runtime.thread is not None and runtime.thread.is_alive():
            raise HTTPException(status_code=400, detail="Wait for transcription to finish.")
        if _current_answer_mode(runtime) != "oral":
            raise HTTPException(status_code=400, detail="Not in spoken-answer mode for this question.")

        study_answer.clear_oral_artifacts(_study_paper_dir(session_id), runtime.current_index)
        runtime.feedback_md = ""
        runtime.feedback_json = None
        runtime.followup_md = ""
        runtime.error = ""
        runtime.status = "idle"

        _study_log(runtime, {"type": "oral_retake"})

    return {"status": "ok", "oralHasRecording": False}


def _openai_complete(system: str, user: str) -> str:
    """
    Adapter matching the ``(system, user) -> str`` signature the study-mode
    feedback builders expect.

    Uses the OpenAI chat completions API directly (rather than the Responses
    API the per-capture vision grader uses) because the post-session prompts
    are pure text.
    """
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL or None,
    )
    resp = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        reasoning_effort=settings.OPENAI_REASONING_EFFORT,
    )
    return (resp.choices[0].message.content or "").strip()


@app.post("/jetson/study-guide/runs/{session_id}/end")
def end_study_run(session_id: str) -> dict:
    """
    End a study run: aggregate every capture, ask the LLM for the student
    feedback + teacher summary, persist them locally, and forward both blobs
    to the central backend as session artifacts.

    The endpoint is defensive on every external dependency:
    - The two builders catch their own errors and return empty defaults.
    - The disk write is wrapped so a missing dir / permission issue doesn't
      block the central upload.
    - The central POST is best-effort (``_post_central`` already swallows
      network errors); a failure there is logged but doesn't fail the request
      so the student isn't blocked from navigating to the review page.
    """
    import json as _json

    with _lock:
        runtime = _study_runs.get(session_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="Study run not found")

    worker = runtime.thread
    if worker is not None and worker.is_alive():
        worker.join()

    session_dir = settings.SESSIONS_DIR / runtime.session_id / "paper"
    captures = aggregate_study_session(session_dir)
    specs = runtime.question_specs or []

    if len(specs) > 1:
        qlist: list[tuple[str, list[str]]] = [
            (spec.text, list(spec.rubric_items or [])) for spec in specs
        ]
        student_fb = dict(
            build_study_student_feedback_multi(
                questions=qlist,
                captures=captures,
                llm_complete_fn=_openai_complete,
            )
        )
        teacher_fb = dict(
            build_study_teacher_summary_multi(
                questions=qlist,
                captures=captures,
                student_feedback=student_fb,
                llm_complete_fn=_openai_complete,
            )
        )
    else:
        student_fb = dict(
            build_study_student_feedback(
                question_text=runtime.question_text or "",
                rubric_items=runtime.rubric_items or [],
                captures=captures,
                llm_complete_fn=_openai_complete,
            )
        )
        teacher_fb = dict(
            build_study_teacher_summary(
                question_text=runtime.question_text or "",
                rubric_items=runtime.rubric_items or [],
                captures=captures,
                student_feedback=student_fb,
                llm_complete_fn=_openai_complete,
            )
        )

    payload = {
        "study_feedback": student_fb,
        "study_teacher_summary": teacher_fb,
    }
    try:
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "study_feedback.json").write_text(
            _json.dumps(payload, indent=2), encoding="utf-8"
        )
    except Exception as e:
        print(f"[jetson_backend] Failed to persist study_feedback.json: {e}")

    # Emit a final end-of-run event and roll the JSONL timeline up into a
    # pretty ``interactions.json`` alongside ``study_feedback.json``.
    _study_log(
        runtime,
        {
            "type": "run_ended",
            "question_count": len(specs) if specs else 1,
        },
    )
    try:
        session_log.finalize(
            session_dir,
            extra={
                "study_feedback": student_fb,
                "study_teacher_summary": teacher_fb,
            },
        )
    except Exception as e:
        print(f"[jetson_backend] Failed to finalize interactions.json: {e}")

    try:
        _write_metrics_artifacts(session_id, runtime)
    except Exception as e:
        print(f"[jetson_backend] Failed to write metrics artifacts: {e}")

    _post_central(
        f"/sessions/{session_id}/artifacts",
        {
            "artifacts": {
                "session_dir_uri": str(session_dir.parent),
                "study_feedback": student_fb,
                "study_teacher_summary": teacher_fb,
                "mode": "study",
            }
        },
    )

    runtime.status = "done"
    runtime.finished_at = datetime.utcnow()
    return {"status": "ok"}


@app.post("/jetson/study-guide/runs/{session_id}/client-event")
async def study_client_event(session_id: str, request: Request) -> dict:
    """
    Accept best-effort telemetry from the student web UI.

    This endpoint is intentionally permissive so it can be called via
    ``navigator.sendBeacon`` (which may use non-JSON content types).
    """
    import json as _json

    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty body")
    try:
        payload = _json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Expected JSON body")

    try:
        evt = StudyClientEventRequest.model_validate(payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    with _lock:
        runtime = _study_runs.get(session_id)

    data = dict(evt.data or {})
    if evt.client_ts_ms is not None:
        data["client_ts_ms"] = int(evt.client_ts_ms)
    _study_log_client_event(
        session_id,
        runtime,
        {
            "type": "client_event",
            "client_event_type": str(evt.type),
            "question_index": int(evt.question_index) if isinstance(evt.question_index, int) else None,
            "data": data,
        },
    )
    return {"status": "ok"}


@app.post("/jetson/study-guide/runs/{session_id}/action")
def study_action(session_id: str, payload: StudyActionRequest) -> dict:
    with _lock:
        runtime = _study_runs.get(session_id)
    if not runtime:
        raise HTTPException(status_code=404, detail="Study run not found")

    if payload.action == "understand":
        runtime.followup_md = "Great — let's move on when you're ready."
        _study_log(
            runtime,
            {
                "type": "helper_action",
                "action": "understand",
                "student_text": (payload.questionText or "").strip() or None,
                "reply_md": runtime.followup_md,
            },
        )
        return {"status": "ok"}

    if payload.action in ("lost", "question", "ama"):
        if runtime.thread is not None and runtime.thread.is_alive():
            raise HTTPException(
                status_code=400,
                detail="Wait for capture or grading to finish before using the tutor chat.",
            )
        if not settings.OPENAI_API_KEY:
            raise HTTPException(status_code=503, detail="OpenAI API key is not configured on this device.")

    if payload.action == "ama":
        q = (payload.questionText or "").strip()
        if not q:
            raise HTTPException(status_code=400, detail="questionText is required for action=ama")
        runtime.ama_turns.append({"role": "user", "content": q})
        _study_log(
            runtime,
            {"type": "ama_turn", "role": "user", "content": q},
        )
        context = _build_study_ama_context(runtime)
        chat_block = _format_ama_chat_for_prompt(runtime.ama_turns)
        prompt = build_study_ama_prompt(context=context, chat_block=chat_block)
        from openai import OpenAI

        client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
        runtime.status = "thinking"
        try:
            resp = client.responses.create(
                model=settings.OPENAI_MODEL,
                input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
                reasoning={"effort": settings.OPENAI_REASONING_EFFORT},
            )
            reply = (getattr(resp, "output_text", "") or "").strip() or (
                "Sorry, I could not form a reply. Please try again."
            )
            runtime.ama_turns.append({"role": "assistant", "content": reply})
            _study_log(
                runtime,
                {
                    "type": "ama_turn",
                    "role": "assistant",
                    "content": reply,
                    "model": settings.OPENAI_MODEL,
                },
            )
        except Exception as e:
            if runtime.ama_turns and runtime.ama_turns[-1].get("role") == "user":
                runtime.ama_turns.pop()
            _study_log(
                runtime,
                {"type": "ama_error", "error": str(e)},
            )
            runtime.status = "done"
            raise HTTPException(status_code=500, detail=str(e)) from e
        runtime.status = "done"
        return {"status": "ok", "reply": reply}

    # For "lost" / "question", call LLM for a short targeted response using the latest context.
    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
    prompt = (
        "You are a warm, supportive teaching assistant. The student is practicing an exam problem — "
        "use a coaching tone; never shame them or use harsh judgment language.\n\n"
        f"Problem:\n{runtime.question_text}\n\n"
        f"Rubric:\n" + "\n".join(f"- {r}" for r in (runtime.rubric_items or [])) + "\n\n"
        "We previously gave the student feedback. Here is that feedback:\n"
        f"{runtime.feedback_md}\n\n"
        "Respond in readable markdown (not JSON). For math, use only KaTeX-safe `$...$` or `$$...$$` with standard LaTeX.\n\n"
    )
    if payload.action == "lost":
        prompt += (
            "The student says: \"I'm lost\".\n"
            "Give a concise, step-by-step explanation, and a small hint for the next step.\n"
            "Do not be overly verbose."
        )
    else:
        q = (payload.questionText or "").strip()
        if not q:
            raise HTTPException(status_code=400, detail="questionText is required for action=question")
        prompt += (
            "The student has a question:\n"
            f"\"{q}\"\n\n"
            "Answer their question clearly and briefly, referencing the problem and rubric."
        )

    runtime.status = "thinking"
    resp = client.responses.create(
        model=settings.OPENAI_MODEL,
        input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        reasoning={"effort": settings.OPENAI_REASONING_EFFORT},
    )
    runtime.followup_md = (getattr(resp, "output_text", "") or "").strip()
    _study_log(
        runtime,
        {
            "type": "helper_action",
            "action": payload.action,
            "student_text": (payload.questionText or "").strip() or None,
            "reply_md": runtime.followup_md,
            "model": settings.OPENAI_MODEL,
        },
    )
    runtime.status = "done"
    return {"status": "ok"}


def _validate_likert(value: Optional[int], field: str) -> None:
    """Ensure a 1-5 Likert rating is either unset or an int in [1, 5]."""
    if value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool) or not (1 <= value <= 5):
        raise HTTPException(
            status_code=400,
            detail=f"{field} must be an integer between 1 and 5",
        )


@app.post("/jetson/study-guide/runs/{session_id}/survey")
def submit_study_exit_survey(
    session_id: str, payload: StudyExitSurveyRequest
) -> dict:
    """Persist the optional end-of-study exit survey.

    Writes ``sessions/<session_id>/paper/survey.json`` and appends a
    ``survey_submitted`` event to the session's ``interactions.jsonl``.

    Intentionally does NOT require a live ``_StudyRuntime``: the survey
    page may load after the run has already been cleared from memory
    (e.g. if the student refreshes after hitting ``/end``).
    """
    import json as _json

    _validate_likert(payload.helpfulness, "helpfulness")
    _validate_likert(payload.ease_of_use, "ease_of_use")
    _validate_likert(payload.question_difficulty, "question_difficulty")

    paper_dir = _study_paper_dir(session_id)
    paper_dir.mkdir(parents=True, exist_ok=True)

    submitted_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    survey_payload: dict[str, Any] = {
        "session_id": session_id,
        "submitted_at": submitted_at,
        "helpfulness": payload.helpfulness,
        "ease_of_use": payload.ease_of_use,
        "question_difficulty": payload.question_difficulty,
        "would_use_again": payload.would_use_again,
        "liked": payload.liked,
        "disliked": payload.disliked,
        "improvements": payload.improvements,
        "anything_else": payload.anything_else,
        "response_feedback": payload.response_feedback,
    }

    try:
        (paper_dir / "survey.json").write_text(
            _json.dumps(survey_payload, indent=2), encoding="utf-8"
        )
    except OSError as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to persist survey.json: {e}"
        ) from e

    # Emit the event into the interaction log. If the runtime still exists
    # we go through ``_study_log`` so the envelope carries ``question_index``;
    # otherwise log directly with the session id only.
    event: dict[str, Any] = {
        "type": "survey_submitted",
        "helpfulness": payload.helpfulness,
        "ease_of_use": payload.ease_of_use,
        "question_difficulty": payload.question_difficulty,
        "would_use_again": payload.would_use_again,
        "liked": payload.liked,
        "disliked": payload.disliked,
        "improvements": payload.improvements,
        "anything_else": payload.anything_else,
        "response_feedback": payload.response_feedback,
        "submitted_at": submitted_at,
    }
    with _lock:
        runtime = _study_runs.get(session_id)
    if runtime is not None:
        _study_log(runtime, event)
    else:
        ctx = _load_study_context(session_id)
        session_log.log_event(
            paper_dir,
            {"session_id": session_id, **event},
        )
        student_id = str(ctx.get("student_id") or "")
        day_run_id = str(ctx.get("day_run_id") or "")
        target_dir = _metrics_session_dir(session_id, student_id, day_run_id)
        if target_dir is not None:
            metrics_log.log_event(
                target_dir / "events.jsonl",
                {
                    "session_id": session_id,
                    "student_id": student_id,
                    "day_run_id": day_run_id,
                    "question_index": -1,
                    **event,
                },
            )

    try:
        _write_metrics_artifacts(session_id, runtime)
    except Exception:
        pass

    return {"status": "ok"}


@app.get("/jetson/exams/{session_id}/state", response_model=ExamState)
def get_exam_state(session_id: str) -> ExamState:
    with _lock:
        runtime = _exams.get(session_id)
    if not runtime:
        raise HTTPException(status_code=404, detail="Exam not found")

    # Pull live status directly from the running proctor so UI reflects
    # question transitions and thinking/listening phases in near real-time.
    live = runtime.proctor.get_live_state()
    live_status = live.get("status")
    if isinstance(live_status, str) and live_status in {"idle", "listening", "speaking", "thinking", "done"}:
        runtime.status = live_status  # type: ignore[assignment]
    runtime.current_question = str(live.get("question") or runtime.current_question or "")
    runtime.transcript_preview = str(
        live.get("transcript_preview") or runtime.transcript_preview or ""
    )

    status = runtime.status
    question = runtime.current_question or "Exam in progress…"
    transcript = runtime.transcript_preview or ""

    return ExamState(
        session_id=session_id,
        status=status,
        questionText=question,
        transcriptPreview=transcript,
    )


@app.post("/jetson/exams/{session_id}/stop")
def stop_exam(session_id: str) -> dict:
    with _lock:
        runtime = _exams.get(session_id)
    if not runtime:
        raise HTTPException(status_code=404, detail="Exam not found")

    runtime.proctor.request_stop()
    runtime.status = "done"
    return {"status": "stopping"}


@app.post("/jetson/exams/{session_id}/done")
def done_speaking(session_id: str) -> dict:
    """
    Web-UI control: signal that the student is done answering the current question.
    This is the HTTP equivalent of pressing Enter in the terminal.
    """
    with _lock:
        runtime = _exams.get(session_id)
    if not runtime:
        raise HTTPException(status_code=404, detail="Exam not found")
    runtime.proctor.request_done()
    return {"status": "ok"}


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/jetson/tts/test")
def tts_test(payload: dict) -> dict:
    """
    Simple endpoint to validate audio output without running an exam.
    Body: {"text": "hello"}
    """
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Missing text")
    try:
        get_tts_client().speak(text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)

