import type {
  AssessmentSessionsResponse,
  AssessmentSummary,
  SessionDetail,
  StudyStudentFeedbackAny,
  StudyTeacherSummary,
} from '../types/assessment'
import { mockAssessments, mockGradeBucketsByAssessment, mockSessions } from '../data/mockAssessments'
import { teacherReviewData } from '../data/teacherReview'

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

function normalizeSessionStatus(status: string): 'pending' | 'ready' | 'reviewed' | 'failed' {
  if (status === 'reviewed') return 'reviewed'
  if (status === 'evidence_ready' || status === 'ready') return 'ready'
  if (status === 'evidence_failed' || status === 'failed') return 'failed'
  return 'pending'
}

export interface TeacherApi {
  getAssessments(): Promise<AssessmentSummary[]>
  getAssessmentSessions(assessmentId: string): Promise<AssessmentSessionsResponse>
  getSession(sessionId: string): Promise<SessionDetail>
  createAssessment(input: {
    title: string
    rubricJson: unknown
    questionSetJson: unknown
  }): Promise<{ assessmentId: number | null }>
}

const mockTeacherApi: TeacherApi = {
  async getAssessments() {
    return mockAssessments
  },

  async getAssessmentSessions(assessmentId) {
    const assessmentSummary =
      mockAssessments.find((a) => a.id === assessmentId) ?? mockAssessments[0]
    const sessions = mockSessions.filter((s) => s.assessmentId === assessmentSummary.id)
    const gradeBuckets =
      mockGradeBucketsByAssessment[assessmentSummary.id] ??
      mockGradeBucketsByAssessment[mockAssessments[0].id]
    return {
      assessment: {
        id: Number.isNaN(Number(assessmentSummary.id))
          ? 1
          : Number(assessmentSummary.id),
        title: assessmentSummary.title,
        description: null,
        status: 'published',
      },
      sessions,
      grade_buckets: gradeBuckets,
    }
  },

  async getSession(sessionId) {
    const session = mockSessions.find((s) => s.id === sessionId) ?? mockSessions[0]
    return {
      session: {
        id: session.id,
        assessmentId: session.assessmentId,
        studentId: undefined,
        studentName: session.studentName,
        dateIso: new Date(session.dateIso),
        status: session.status,
        score: session.score,
      },
      evidencePacket: {
        sessionId: session.id,
        rubricId: 1,
        packetJson: {
          summaryTitle: teacherReviewData.summaryTitle,
          summaryBody: teacherReviewData.summaryBody,
          suggestedGrade: teacherReviewData.suggestedGrade,
        },
      },
      artifacts: {},
      review: null,
      question_reviews: [],
      session_screenshots: [],
      study_feedback: null,
      study_teacher_summary: null,
    }
  },

  async createAssessment() {
    // In mock mode we don't persist; return null to indicate no real backend id.
    return { assessmentId: null }
  },
}

const realTeacherApi: TeacherApi = {
  async getAssessments() {
    if (!CENTRAL_API_BASE_URL) return mockTeacherApi.getAssessments()
    const rows = await httpJson<
      Array<{
        id: number
        title: string
        total_sessions: number
        unreviewed_sessions: number
      }>
    >(`${CENTRAL_API_BASE_URL}/assessments`)
    return rows.map((row) => ({
      id: String(row.id),
      title: row.title,
      totalSessions: row.total_sessions,
      unreviewedSessions: row.unreviewed_sessions,
    }))
  },

  async getAssessmentSessions(assessmentId) {
    if (!CENTRAL_API_BASE_URL) return mockTeacherApi.getAssessmentSessions(assessmentId)
    const payload = await httpJson<{
      assessment: {
        id: number
        title: string
        description?: string | null
        status: string
      }
      sessions: Array<{
        id: string
        assessment_id: number
        student_id?: number | null
        student_name?: string | null
        date_iso?: string | null
        status: string
        score?: number | null
      }>
      grade_buckets: Array<{ label: string; count: number }>
    }>(
      `${CENTRAL_API_BASE_URL}/assessments/${encodeURIComponent(assessmentId)}/sessions`,
    )
    return {
      assessment: payload.assessment,
      sessions: payload.sessions.map((s) => ({
        id: s.id,
        assessmentId: String(s.assessment_id),
        studentName: s.student_name ?? 'Student',
        dateIso: s.date_iso ?? new Date().toISOString(),
        status: normalizeSessionStatus(s.status),
        score: s.score ?? null,
      })),
      grade_buckets: payload.grade_buckets,
    }
  },

  async getSession(sessionId) {
    if (!CENTRAL_API_BASE_URL) return mockTeacherApi.getSession(sessionId)
    const payload = await httpJson<{
      session: {
        id: string
        assessment_id: number
        student_id?: number | null
        student_name?: string | null
        date_iso?: string | null
        status: string
        score?: number | null
      }
      evidence_packet?: {
        session_id: string
        rubric_id: number
        packet_json: unknown
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
      study_feedback?: StudyStudentFeedbackAny | null
      study_teacher_summary?: StudyTeacherSummary | null
    }>(`${CENTRAL_API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}`)
    const normalized: SessionDetail = {
      session: {
        id: payload.session.id,
        assessmentId: payload.session.assessment_id,
        studentId: payload.session.student_id ?? null,
        studentName: payload.session.student_name ?? null,
        dateIso: payload.session.date_iso ?? null,
        status: normalizeSessionStatus(payload.session.status),
        score: payload.session.score ?? null,
      },
      evidence_packet: payload.evidence_packet
        ? {
            sessionId: payload.evidence_packet.session_id,
            rubricId: payload.evidence_packet.rubric_id,
            packetJson: payload.evidence_packet.packet_json,
          }
        : null,
      artifacts: payload.artifacts ?? {},
      review: payload.review ?? null,
      question_reviews: payload.question_reviews ?? [],
      session_screenshots: payload.session_screenshots ?? [],
      study_feedback: payload.study_feedback ?? null,
      study_teacher_summary: payload.study_teacher_summary ?? null,
    }
    return normalized
  },

  async createAssessment(input) {
    if (!CENTRAL_API_BASE_URL) return mockTeacherApi.createAssessment(input)
    // 1) Create rubric
    const rubric = await httpJson<{ id: number }>(`${CENTRAL_API_BASE_URL}/rubrics`, {
      method: 'POST',
      body: JSON.stringify({
        title: input.title,
        subject: null,
        rubric_json: input.rubricJson,
      }),
    })
    // 2) Create question set
    const questionSet = await httpJson<{ id: number }>(`${CENTRAL_API_BASE_URL}/question-sets`, {
      method: 'POST',
      body: JSON.stringify({
        title: input.title,
        subject: null,
        question_set_json: input.questionSetJson,
      }),
    })
    // 3) Create assessment
    const assessment = await httpJson<{ id: number }>(`${CENTRAL_API_BASE_URL}/assessments`, {
      method: 'POST',
      body: JSON.stringify({
        rubric_id: rubric.id,
        question_set_id: questionSet.id,
        title: input.title,
        description: null,
      }),
    })
    return { assessmentId: assessment.id }
  },
}

export const teacherApi: TeacherApi = CENTRAL_API_BASE_URL ? realTeacherApi : mockTeacherApi

