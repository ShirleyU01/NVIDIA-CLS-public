import type {
  StudyDashboardSessionRow,
  StudyDashboardSummary,
  StudyDashboardTopicRow,
  StudyDashboardTotals,
} from '../types/studyDashboard'

const CENTRAL_API_BASE_URL = import.meta.env.VITE_CENTRAL_API_BASE_URL

async function httpJson<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const res = await fetch(input, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`)
  }
  return (await res.json()) as T
}

type RawTotals = {
  sessions: number
  study_sessions_started: number
  students: number
  activated_sessions: number
  activation_rate: number
  completed_sessions: number
  completion_rate: number
  reached_post_session_summary_count: number
  reached_post_session_summary_rate: number
  survey_submissions: number
  survey_submit_rate: number
  repeated_usage_yes_count: number
  repeated_usage_response_count: number
  repeated_usage_rate: number | null
  avg_helpfulness: number | null
  avg_ease_of_use: number | null
  avg_question_difficulty: number | null
  avg_session_duration_ms: number | null
  avg_grade_duration_ms: number | null
  avg_time_to_first_capture_ms: number | null
  avg_time_working_ms: number | null
  avg_questions_per_session: number | null
  avg_percent_correct_questions: number | null
  jetson_backend_error_rate: number | null
  total_questions: number
  total_captures: number
  total_ama_turns: number
  backend_error_count: number
  client_error_count: number
  questions_answered_oral: number
  questions_answered_paper: number
  oral_upload_count: number
  oral_transcript_count: number
  oral_retake_count: number
  oral_record_started_count: number
  avg_oral_record_duration_ms: number | null
  avg_transcription_duration_ms: number | null
  p95_transcription_duration_ms: number | null
  avg_upload_to_transcript_ms: number | null
  avg_paper_grade_duration_ms: number | null
  avg_oral_grade_duration_ms: number | null
  p95_oral_grade_duration_ms: number | null
  oral_transcript_total_chars: number
}

type RawSession = {
  session_id: string
  student_id: string
  day_run_id: string
  course: string
  topic_id: string
  requested_count: number | null
  event_count: number
  study_sessions_started: number
  question_count: number
  capture_count: number
  activated: boolean
  ama_user_count: number
  grade_count: number
  session_completed: boolean
  reached_post_session_summary: boolean
  survey_submitted: boolean
  survey_helpfulness: number | null
  survey_ease_of_use: number | null
  survey_question_difficulty: number | null
  survey_would_use_again: boolean | null
  survey_liked: string
  survey_disliked: string
  survey_improvements: string
  survey_anything_else: string
  survey_response_feedback: string
  session_duration_ms: number | null
  avg_grade_duration_ms: number | null
  time_to_first_capture_ms: number | null
  avg_time_working_ms: number | null
  percent_correct_questions: number | null
  questions_with_repeat_attempts: number
  backend_error_count: number
  client_error_count: number
  jetson_backend_error_rate: number | null
  questions_answered_oral: number
  questions_answered_paper: number
  oral_upload_count: number
  oral_transcript_count: number
  oral_retake_count: number
  oral_record_started_count: number
  avg_oral_record_duration_ms: number | null
  avg_transcription_duration_ms: number | null
  upload_to_transcript_ms: number | null
  avg_paper_grade_duration_ms: number | null
  avg_oral_grade_duration_ms: number | null
  oral_transcript_total_chars: number
}

type RawTopic = {
  course: string
  topic_id: string
  sessions: number
  completion_rate: number
  avg_helpfulness: number | null
  avg_percent_correct_questions: number | null
  avg_grade_duration_ms: number | null
  questions_answered_oral: number
  questions_answered_paper: number
  oral_transcript_count: number
  avg_transcription_duration_ms: number | null
  avg_oral_grade_duration_ms: number | null
}

type RawSummary = {
  generated_at: string
  source_root: string
  totals: RawTotals
  sessions: RawSession[]
  topics: RawTopic[]
  malformed_files: number
}

const mapTotals = (raw: RawTotals): StudyDashboardTotals => ({
  sessions: raw.sessions,
  studySessionsStarted: raw.study_sessions_started,
  students: raw.students,
  activatedSessions: raw.activated_sessions ?? 0,
  activationRate: raw.activation_rate ?? 0,
  completedSessions: raw.completed_sessions,
  completionRate: raw.completion_rate,
  reachedPostSessionSummaryCount: raw.reached_post_session_summary_count,
  reachedPostSessionSummaryRate: raw.reached_post_session_summary_rate,
  surveySubmissions: raw.survey_submissions,
  surveySubmitRate: raw.survey_submit_rate,
  repeatedUsageYesCount: raw.repeated_usage_yes_count,
  repeatedUsageResponseCount: raw.repeated_usage_response_count,
  repeatedUsageRate: raw.repeated_usage_rate,
  avgHelpfulness: raw.avg_helpfulness,
  avgEaseOfUse: raw.avg_ease_of_use,
  avgQuestionDifficulty: raw.avg_question_difficulty,
  avgSessionDurationMs: raw.avg_session_duration_ms,
  avgGradeDurationMs: raw.avg_grade_duration_ms,
  avgTimeToFirstCaptureMs: raw.avg_time_to_first_capture_ms,
  avgTimeWorkingMs: raw.avg_time_working_ms,
  avgQuestionsPerSession: raw.avg_questions_per_session,
  avgPercentCorrectQuestions: raw.avg_percent_correct_questions,
  jetsonBackendErrorRate: raw.jetson_backend_error_rate,
  totalQuestions: raw.total_questions,
  totalCaptures: raw.total_captures,
  totalAmaTurns: raw.total_ama_turns,
  backendErrorCount: raw.backend_error_count,
  clientErrorCount: raw.client_error_count,
  questionsAnsweredOral: raw.questions_answered_oral ?? 0,
  questionsAnsweredPaper: raw.questions_answered_paper ?? 0,
  oralUploadCount: raw.oral_upload_count ?? 0,
  oralTranscriptCount: raw.oral_transcript_count ?? 0,
  oralRetakeCount: raw.oral_retake_count ?? 0,
  oralRecordStartedCount: raw.oral_record_started_count ?? 0,
  avgOralRecordDurationMs: raw.avg_oral_record_duration_ms,
  avgTranscriptionDurationMs: raw.avg_transcription_duration_ms,
  p95TranscriptionDurationMs: raw.p95_transcription_duration_ms,
  avgUploadToTranscriptMs: raw.avg_upload_to_transcript_ms,
  avgPaperGradeDurationMs: raw.avg_paper_grade_duration_ms,
  avgOralGradeDurationMs: raw.avg_oral_grade_duration_ms,
  p95OralGradeDurationMs: raw.p95_oral_grade_duration_ms,
  oralTranscriptTotalChars: raw.oral_transcript_total_chars ?? 0,
})

const mapSession = (raw: RawSession): StudyDashboardSessionRow => ({
  sessionId: raw.session_id,
  studentId: raw.student_id,
  dayRunId: raw.day_run_id,
  course: raw.course,
  topicId: raw.topic_id,
  requestedCount: raw.requested_count,
  eventCount: raw.event_count,
  studySessionsStarted: raw.study_sessions_started,
  questionCount: raw.question_count,
  captureCount: raw.capture_count,
  activated: raw.activated ?? (raw.capture_count > 0 || (raw.oral_transcript_count ?? 0) > 0),
  amaUserCount: raw.ama_user_count,
  gradeCount: raw.grade_count,
  sessionCompleted: raw.session_completed,
  reachedPostSessionSummary: raw.reached_post_session_summary,
  surveySubmitted: raw.survey_submitted,
  surveyHelpfulness: raw.survey_helpfulness,
  surveyEaseOfUse: raw.survey_ease_of_use,
  surveyQuestionDifficulty: raw.survey_question_difficulty,
  surveyWouldUseAgain: raw.survey_would_use_again,
  surveyLiked: raw.survey_liked,
  surveyDisliked: raw.survey_disliked,
  surveyImprovements: raw.survey_improvements,
  surveyAnythingElse: raw.survey_anything_else,
  surveyResponseFeedback: raw.survey_response_feedback,
  sessionDurationMs: raw.session_duration_ms,
  avgGradeDurationMs: raw.avg_grade_duration_ms,
  timeToFirstCaptureMs: raw.time_to_first_capture_ms,
  avgTimeWorkingMs: raw.avg_time_working_ms,
  percentCorrectQuestions: raw.percent_correct_questions,
  questionsWithRepeatAttempts: raw.questions_with_repeat_attempts,
  backendErrorCount: raw.backend_error_count,
  clientErrorCount: raw.client_error_count,
  jetsonBackendErrorRate: raw.jetson_backend_error_rate,
  questionsAnsweredOral: raw.questions_answered_oral ?? 0,
  questionsAnsweredPaper: raw.questions_answered_paper ?? 0,
  oralUploadCount: raw.oral_upload_count ?? 0,
  oralTranscriptCount: raw.oral_transcript_count ?? 0,
  oralRetakeCount: raw.oral_retake_count ?? 0,
  oralRecordStartedCount: raw.oral_record_started_count ?? 0,
  avgOralRecordDurationMs: raw.avg_oral_record_duration_ms,
  avgTranscriptionDurationMs: raw.avg_transcription_duration_ms,
  uploadToTranscriptMs: raw.upload_to_transcript_ms,
  avgPaperGradeDurationMs: raw.avg_paper_grade_duration_ms,
  avgOralGradeDurationMs: raw.avg_oral_grade_duration_ms,
  oralTranscriptTotalChars: raw.oral_transcript_total_chars ?? 0,
})

const mapTopic = (raw: RawTopic): StudyDashboardTopicRow => ({
  course: raw.course,
  topicId: raw.topic_id,
  sessions: raw.sessions,
  completionRate: raw.completion_rate,
  avgHelpfulness: raw.avg_helpfulness,
  avgPercentCorrectQuestions: raw.avg_percent_correct_questions,
  avgGradeDurationMs: raw.avg_grade_duration_ms,
  questionsAnsweredOral: raw.questions_answered_oral ?? 0,
  questionsAnsweredPaper: raw.questions_answered_paper ?? 0,
  oralTranscriptCount: raw.oral_transcript_count ?? 0,
  avgTranscriptionDurationMs: raw.avg_transcription_duration_ms,
  avgOralGradeDurationMs: raw.avg_oral_grade_duration_ms,
})

export async function getStudyDashboardSummary(): Promise<StudyDashboardSummary> {
  if (!CENTRAL_API_BASE_URL) {
    return {
      generatedAt: new Date().toISOString(),
      sourceRoot: '',
      totals: {
        sessions: 0,
        studySessionsStarted: 0,
        students: 0,
        activatedSessions: 0,
        activationRate: 0,
        completedSessions: 0,
        completionRate: 0,
        reachedPostSessionSummaryCount: 0,
        reachedPostSessionSummaryRate: 0,
        surveySubmissions: 0,
        surveySubmitRate: 0,
        repeatedUsageYesCount: 0,
        repeatedUsageResponseCount: 0,
        repeatedUsageRate: null,
        avgHelpfulness: null,
        avgEaseOfUse: null,
        avgQuestionDifficulty: null,
        avgSessionDurationMs: null,
        avgGradeDurationMs: null,
        avgTimeToFirstCaptureMs: null,
        avgTimeWorkingMs: null,
        avgQuestionsPerSession: null,
        avgPercentCorrectQuestions: null,
        jetsonBackendErrorRate: null,
        totalQuestions: 0,
        totalCaptures: 0,
        totalAmaTurns: 0,
        backendErrorCount: 0,
        clientErrorCount: 0,
        questionsAnsweredOral: 0,
        questionsAnsweredPaper: 0,
        oralUploadCount: 0,
        oralTranscriptCount: 0,
        oralRetakeCount: 0,
        oralRecordStartedCount: 0,
        avgOralRecordDurationMs: null,
        avgTranscriptionDurationMs: null,
        p95TranscriptionDurationMs: null,
        avgUploadToTranscriptMs: null,
        avgPaperGradeDurationMs: null,
        avgOralGradeDurationMs: null,
        p95OralGradeDurationMs: null,
        oralTranscriptTotalChars: 0,
      },
      sessions: [],
      topics: [],
      malformedFiles: 0,
    }
  }

  const raw = await httpJson<RawSummary>(`${CENTRAL_API_BASE_URL}/study-dashboard/summary`)
  return {
    generatedAt: raw.generated_at,
    sourceRoot: raw.source_root,
    totals: mapTotals(raw.totals),
    sessions: raw.sessions.map(mapSession),
    topics: raw.topics.map(mapTopic),
    malformedFiles: raw.malformed_files,
  }
}
