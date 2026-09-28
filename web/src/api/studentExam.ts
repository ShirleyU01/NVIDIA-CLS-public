import type { ExamState, ExamStatus } from '../types/exam'
import { getTeacherBasicAuthHeaderValue, isTeacherAuthed } from '../auth/teacherAuth'

// Minimal API surface for the student / Jetson integration.
// In the real system these functions will call a Jetson-local backend
// that wraps jetson_runtime/proctor.py and the central backend /sessions API.

export interface CreateSessionRequest {
  assessmentId: string
  studentId?: string
}

export interface CreateSessionResponse {
  sessionId: string
}

export interface StudentExamApi {
  createSession(input: CreateSessionRequest): Promise<CreateSessionResponse>
  getExamState(sessionId: string): Promise<ExamState>
  doneSpeaking(sessionId: string): Promise<void>
  endExam(sessionId: string): Promise<void>
}

// Placeholder implementation that simulates the API locally so the UI
// can be exercised without a running backend.

let mockSessionIdCounter = 1

const JETSON_API_BASE_URL = import.meta.env.VITE_JETSON_API_BASE_URL ?? 'http://localhost:8001'
const CENTRAL_API_BASE_URL = import.meta.env.VITE_CENTRAL_API_BASE_URL

async function httpJson<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const { headers: initHeaders, ...restInit } = init ?? {}
  const res = await fetch(input, {
    ...restInit,
    headers: { 'Content-Type': 'application/json', ...(initHeaders ?? {}) },
  })
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`)
  }
  return (await res.json()) as T
}

interface BackendExamState {
  session_id: string
  status: ExamStatus
  questionText: string
  transcriptPreview: string
}

export const studentExamApi: StudentExamApi = {
  async createSession(input) {
    if (CENTRAL_API_BASE_URL) {
      const assessmentIdNum = Number(input.assessmentId)
      if (Number.isNaN(assessmentIdNum)) {
        throw new Error(`Invalid assessment id: ${input.assessmentId}`)
      }

      const examConfigResp = await httpJson<{ exam_config: unknown }>(
        `${CENTRAL_API_BASE_URL}/assessments/${encodeURIComponent(input.assessmentId)}/exam-config`,
      )

      const centralSession = await httpJson<{ id: string }>(`${CENTRAL_API_BASE_URL}/sessions`, {
        method: 'POST',
        headers: isTeacherAuthed() ? { Authorization: getTeacherBasicAuthHeaderValue() } : undefined,
        body: JSON.stringify({
          assessment_id: assessmentIdNum,
          student_id: input.studentId ? Number(input.studentId) : null,
          device_info: { source: 'web-student-ui' },
        }),
      })

      const sessionId = centralSession.id
      await httpJson<unknown>(`${JETSON_API_BASE_URL}/jetson/exams`, {
        method: 'POST',
        body: JSON.stringify({
          session_id: sessionId,
          exam_config: examConfigResp.exam_config,
        }),
      })
      return { sessionId }
    }

    // Mock/dev fallback when central backend is not configured.
    const sessionId = `session-${mockSessionIdCounter++}`
    await httpJson<unknown>(`${JETSON_API_BASE_URL}/jetson/exams`, {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId }),
    })
    return { sessionId }
  },

  async getExamState(sessionId) {
    const state = await httpJson<BackendExamState>(
      `${JETSON_API_BASE_URL}/jetson/exams/${encodeURIComponent(sessionId)}/state`,
    )
    const normalized: ExamState = {
      sessionId: state.session_id,
      status: state.status,
      questionText: state.questionText,
      transcriptPreview: state.transcriptPreview,
    }
    return normalized
  },

  async doneSpeaking(sessionId) {
    await httpJson<unknown>(`${JETSON_API_BASE_URL}/jetson/exams/${encodeURIComponent(sessionId)}/done`, {
      method: 'POST',
    })
  },

  async endExam(sessionId) {
    await httpJson<unknown>(`${JETSON_API_BASE_URL}/jetson/exams/${encodeURIComponent(sessionId)}/stop`, {
      method: 'POST',
    })
  },
}

