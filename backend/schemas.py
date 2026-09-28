from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class RubricCreate(BaseModel):
    title: str
    subject: Optional[str] = None
    rubric_json: Dict[str, Any]


class RubricRead(BaseModel):
    id: int
    title: str
    subject: Optional[str] = None
    rubric_json: Dict[str, Any]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class QuestionSetCreate(BaseModel):
    title: str
    subject: Optional[str] = None
    question_set_json: Dict[str, Any]


class QuestionSetRead(BaseModel):
    id: int
    title: str
    subject: Optional[str] = None
    question_set_json: Dict[str, Any]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class AssessmentCreate(BaseModel):
    rubric_id: int
    question_set_id: int
    title: str
    description: Optional[str] = None


class AssessmentPublish(BaseModel):
    publish_settings: Optional[Dict[str, Any]] = None


class AssessmentSummary(BaseModel):
    id: int
    title: str
    total_sessions: int = 0
    unreviewed_sessions: int = 0


class AssessmentRead(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    status: str
    rubric_id: Optional[int] = None
    question_set_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class SessionCreate(BaseModel):
    assessment_id: int
    student_id: Optional[int] = None
    device_info: Optional[Dict[str, Any]] = None


class StudySeenRecord(BaseModel):
    student_id: int = Field(ge=1)
    course: Optional[str] = None
    topic_id: Optional[str] = None
    question_ids: List[str] = Field(default_factory=list)
    finalize: bool = True


class SessionArtifactsUpdate(BaseModel):
    artifacts: Dict[str, Any]


class StudySurveyStatusRead(BaseModel):
    student_id: int
    completed: bool


class StudySurveyCompletionUpdate(BaseModel):
    skipped: bool = False


class SessionArtifactUpdate(BaseModel):
    recording_uri: Optional[str] = None
    final_transcript_uri: Optional[str] = None
    transcript_uri: Optional[str] = None
    session_dir_uri: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class SessionSummary(BaseModel):
    id: str
    assessment_id: int
    student_id: Optional[int] = None
    student_name: Optional[str] = None
    date_iso: Optional[datetime] = None
    status: str
    score: Optional[float] = None

    @field_serializer("date_iso")
    def serialize_date_iso(self, dt: Optional[datetime]) -> Optional[str]:
        """Serialize as ISO with Z so frontend parses as UTC (backend stores naive UTC)."""
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.isoformat() + "Z"
        return dt.isoformat()


class SessionRead(BaseModel):
    id: str
    assessment_id: Optional[int] = None
    student_id: Optional[int] = None
    status: str
    evidence_packet_status: str
    artifacts: Optional[Dict[str, Any]] = None
    score_total: Optional[float] = None
    score_max: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class GradeBucket(BaseModel):
    label: str
    count: int


class AssessmentSessionsResponse(BaseModel):
    assessment: AssessmentRead
    sessions: List[SessionSummary]
    grade_buckets: List[GradeBucket] = Field(default_factory=list)


class EvidencePacketRead(BaseModel):
    session_id: str
    rubric_id: int
    packet_json: Dict[str, Any]


class SessionDetail(BaseModel):
    session: SessionSummary
    evidence_packet: Optional[EvidencePacketRead] = None
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    review: Optional[Dict[str, Any]] = None
    question_reviews: List[Dict[str, Any]] = Field(default_factory=list)
    session_screenshots: List[Dict[str, Any]] = Field(default_factory=list)
    # Study-mode post-session feedback. Both blobs are written by the Jetson
    # ``/jetson/study-guide/runs/:id/end`` endpoint into ``Session.artifacts``
    # and surfaced here through ``backend.routes.sessions._extract_study_*``
    # helpers. Both default to ``None`` so exam-mode sessions are unaffected.
    study_feedback: Optional[Dict[str, Any]] = None
    study_teacher_summary: Optional[Dict[str, Any]] = None


class SessionDetailRead(BaseModel):
    session: SessionRead
    evidence_packet: Optional[EvidencePacketRead] = None


class StudyDashboardTotals(BaseModel):
    sessions: int = 0
    study_sessions_started: int = 0
    students: int = 0
    activated_sessions: int = 0
    activation_rate: float = 0.0
    completed_sessions: int = 0
    completion_rate: float = 0.0
    reached_post_session_summary_count: int = 0
    reached_post_session_summary_rate: float = 0.0
    survey_submissions: int = 0
    survey_submit_rate: float = 0.0
    repeated_usage_yes_count: int = 0
    repeated_usage_response_count: int = 0
    repeated_usage_rate: Optional[float] = None
    avg_helpfulness: Optional[float] = None
    avg_ease_of_use: Optional[float] = None
    avg_question_difficulty: Optional[float] = None
    avg_session_duration_ms: Optional[float] = None
    avg_grade_duration_ms: Optional[float] = None
    avg_time_to_first_capture_ms: Optional[float] = None
    avg_time_working_ms: Optional[float] = None
    avg_questions_per_session: Optional[float] = None
    avg_percent_correct_questions: Optional[float] = None
    jetson_backend_error_rate: Optional[float] = None
    total_questions: int = 0
    total_captures: int = 0
    total_ama_turns: int = 0
    backend_error_count: int = 0
    client_error_count: int = 0
    questions_answered_oral: int = 0
    questions_answered_paper: int = 0
    oral_upload_count: int = 0
    oral_transcript_count: int = 0
    oral_retake_count: int = 0
    oral_record_started_count: int = 0
    avg_oral_record_duration_ms: Optional[float] = None
    avg_transcription_duration_ms: Optional[float] = None
    p95_transcription_duration_ms: Optional[float] = None
    avg_upload_to_transcript_ms: Optional[float] = None
    avg_paper_grade_duration_ms: Optional[float] = None
    avg_oral_grade_duration_ms: Optional[float] = None
    p95_oral_grade_duration_ms: Optional[float] = None
    oral_transcript_total_chars: int = 0


class StudyDashboardSessionRow(BaseModel):
    session_id: str
    student_id: str
    day_run_id: str
    course: str = ""
    topic_id: str = ""
    requested_count: Optional[int] = None
    event_count: int = 0
    study_sessions_started: int = 0
    question_count: int = 0
    capture_count: int = 0
    activated: bool = False
    ama_user_count: int = 0
    grade_count: int = 0
    session_completed: bool = False
    reached_post_session_summary: bool = False
    survey_submitted: bool = False
    survey_helpfulness: Optional[float] = None
    survey_ease_of_use: Optional[float] = None
    survey_question_difficulty: Optional[float] = None
    survey_would_use_again: Optional[bool] = None
    survey_liked: str = ""
    survey_disliked: str = ""
    survey_improvements: str = ""
    survey_anything_else: str = ""
    survey_response_feedback: str = ""
    session_duration_ms: Optional[int] = None
    avg_grade_duration_ms: Optional[float] = None
    time_to_first_capture_ms: Optional[int] = None
    avg_time_working_ms: Optional[float] = None
    percent_correct_questions: Optional[float] = None
    questions_with_repeat_attempts: int = 0
    backend_error_count: int = 0
    client_error_count: int = 0
    jetson_backend_error_rate: Optional[float] = None
    questions_answered_oral: int = 0
    questions_answered_paper: int = 0
    oral_upload_count: int = 0
    oral_transcript_count: int = 0
    oral_retake_count: int = 0
    oral_record_started_count: int = 0
    avg_oral_record_duration_ms: Optional[float] = None
    avg_transcription_duration_ms: Optional[float] = None
    upload_to_transcript_ms: Optional[float] = None
    avg_paper_grade_duration_ms: Optional[float] = None
    avg_oral_grade_duration_ms: Optional[float] = None
    oral_transcript_total_chars: int = 0


class StudyDashboardTopicRow(BaseModel):
    course: str = ""
    topic_id: str = ""
    sessions: int = 0
    completion_rate: float = 0.0
    avg_helpfulness: Optional[float] = None
    avg_percent_correct_questions: Optional[float] = None
    avg_grade_duration_ms: Optional[float] = None
    questions_answered_oral: int = 0
    questions_answered_paper: int = 0
    oral_transcript_count: int = 0
    avg_transcription_duration_ms: Optional[float] = None
    avg_oral_grade_duration_ms: Optional[float] = None


class StudyDashboardSummary(BaseModel):
    generated_at: datetime
    source_root: str
    totals: StudyDashboardTotals
    sessions: List[StudyDashboardSessionRow] = Field(default_factory=list)
    topics: List[StudyDashboardTopicRow] = Field(default_factory=list)
    malformed_files: int = 0


class SessionReviewCreate(BaseModel):
    final_scores: Optional[Dict[str, Any]] = None
    comments: Optional[str] = None
    flags: Optional[Dict[str, Any]] = None


class SessionReviewRead(BaseModel):
    id: int
    session_id: str
    final_scores: Optional[Dict[str, Any]] = None
    comments: Optional[str] = None
    flags: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class AssessmentSessionsReadItem(BaseModel):
    session_id: str
    student_id: Optional[int] = None
    started_at: Optional[datetime] = None
    status: str
    evidence_packet_status: str
    score_total: Optional[float] = None
    score_max: Optional[float] = None


class AssessmentSessionsRead(BaseModel):
    assessment_id: int
    sessions: List[AssessmentSessionsReadItem]

