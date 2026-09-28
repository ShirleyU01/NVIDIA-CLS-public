import type { StudyStudentFeedback, StudyStudentFeedbackAny, StudyTeacherSummary } from './studyFeedback'

// Re-exported so the rest of the app can import study contracts from
// ``../types/assessment`` like every other session-related type.
export type {
  StudyStudentFeedback,
  StudyStudentFeedbackAny,
  StudyTeacherSummary,
} from './studyFeedback'

export type AssessmentSummary = {
  id: string
  title: string
  totalSessions: number
  unreviewedSessions: number
}

export type SessionStatus = 'pending' | 'ready' | 'reviewed' | 'failed'

export type SessionSummary = {
  id: string
  assessmentId: string
  studentName: string
  dateIso: string
  status: SessionStatus
  score: number | null
}

export type GradeBucket = {
  label: string
  count: number
}

export type AssessmentSessionsResponse = {
  assessment: {
    id: number
    title: string
    description?: string | null
    status: string
  }
  sessions: SessionSummary[]
  grade_buckets: GradeBucket[]
}

export type SessionDetail = {
  session: {
    id: string
    assessmentId: string | number
    studentId?: number | null
    studentName?: string | null
    dateIso?: Date | string | null
    status: string
    score?: number | null
  }
  evidence_packet?: {
    sessionId: string
    rubricId: number
    packetJson: unknown
  } | null
  artifacts: Record<string, unknown>
  review: Record<string, unknown> | null
  question_reviews?: Array<{
    index: number
    question: string
    answer: string
    rubric_items: string[]
  }>
  session_screenshots?: Array<{
    question_number: number
    t: number
    path: string
    trigger_word: string
  }>
  // Post-session feedback for study mode. Both default to ``null`` for exam
  // sessions and for study sessions whose Jetson "/end" upload hasn't landed
  // yet. See ``backend/routes/sessions.py::_extract_study_*``.
  study_feedback?: StudyStudentFeedbackAny | null
  study_teacher_summary?: StudyTeacherSummary | null
}


