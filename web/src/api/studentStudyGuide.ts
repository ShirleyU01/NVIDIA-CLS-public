import type { StudyAnswerMode, StudyRunState } from '../types/studyGuide'
import type { PracticeQuestionPayload } from './questionBank'
import { getTeacherBasicAuthHeaderValue } from '../auth/teacherAuth'

const JETSON_API_BASE_URL = import.meta.env.VITE_JETSON_API_BASE_URL ?? 'http://localhost:8001'
const CENTRAL_API_BASE_URL = import.meta.env.VITE_CENTRAL_API_BASE_URL

async function httpJson<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const { headers: initHeaders, ...restInit } = init ?? {}
  const res = await fetch(input, {
    ...restInit,
    headers: { 'Content-Type': 'application/json', ...(initHeaders ?? {}) },
  })
  if (!res.ok) {
    const err = new Error(`Request failed: ${res.status} ${res.statusText}`)
    ;(err as Error & { status?: number }).status = res.status
    throw err
  }
  return (await res.json()) as T
}

export interface StudyPlanDeviceInfo {
  course: string
  topic_id: string
  requested_count: number
  question_ids: string[]
  /** Duplicated here so seen-question history survives if the session row lacks student_id. */
  student_id?: number
}

export interface CreateStudyRunRequest {
  assessmentId: string
  studentId?: string
  dayRunId?: string
  /** Question-bank practice set from central selection; when non-empty, Jetson uses these instead of exam_config. */
  practiceQuestions?: PracticeQuestionPayload[]
  studyPlan?: StudyPlanDeviceInfo
}

export interface CreateStudyRunResponse {
  sessionId: string
}

interface BackendStudyState {
  session_id: string
  status: StudyRunState['status']
  questionText: string
  feedbackMarkdown: string
  followUpMarkdown: string
  latestImageUrl: string
  error: string
  captureCount?: number
  captureLimit?: number
  questionIndex?: number
  questionCount?: number
  hints?: string[]
  ama_turns?: { role: string; content: string }[]
  answerMode?: StudyAnswerMode
  oralTranscript?: string
  oralHasRecording?: boolean
}

const practiceStorageKey = (sessionId: string) => `study:practiceQuestions:${sessionId}`
const studyPlanStorageKey = (sessionId: string) => `study:studyPlan:${sessionId}`
const completedQuestionIdsKey = (sessionId: string) => `study:completedQuestionIds:${sessionId}`

function getStoredCompletedQuestionIds(sessionId: string): string[] {
  try {
    const raw = window.sessionStorage.getItem(completedQuestionIdsKey(sessionId))
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed.filter((id): id is string => typeof id === 'string' && id.trim().length > 0)
  } catch {
    return []
  }
}

function readStoredStudyPlan(sessionId: string): StudyPlanDeviceInfo | null {
  try {
    const raw = window.sessionStorage.getItem(studyPlanStorageKey(sessionId))
    if (!raw) return null
    return JSON.parse(raw) as StudyPlanDeviceInfo
  } catch {
    return null
  }
}

function addStoredCompletedQuestionId(sessionId: string, questionId: string): string[] {
  const clean = questionId.trim()
  if (!clean) return getStoredCompletedQuestionIds(sessionId)
  const existing = getStoredCompletedQuestionIds(sessionId)
  if (existing.includes(clean)) return existing
  const next = [...existing, clean]
  try {
    window.sessionStorage.setItem(completedQuestionIdsKey(sessionId), JSON.stringify(next))
    const plan = readStoredStudyPlan(sessionId)
    if (plan) {
      window.sessionStorage.setItem(
        studyPlanStorageKey(sessionId),
        JSON.stringify({ ...plan, question_ids: next }),
      )
    }
  } catch {
    // ignore
  }
  return next
}

async function recordStudySeenToCentral(
  sessionId: string,
  questionIds: string[],
  options?: { finalize?: boolean },
): Promise<void> {
  if (!CENTRAL_API_BASE_URL) return
  const cleanIds = questionIds.map((id) => id.trim()).filter(Boolean)
  if (cleanIds.length === 0) return

  let studentId = ''
  try {
    studentId =
      window.sessionStorage.getItem(`study:studentId:${sessionId}`) ??
      window.sessionStorage.getItem('study:studentId') ??
      ''
  } catch {
    studentId = ''
  }
  const numericStudentId = Number(studentId)
  if (!Number.isFinite(numericStudentId) || numericStudentId <= 0) {
    return
  }

  const studyPlan = readStoredStudyPlan(sessionId)
  if (!studyPlan && cleanIds.length === 0) {
    return
  }

  try {
    await httpJson<unknown>(
      `${CENTRAL_API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}/study-seen`,
      {
        method: 'POST',
        headers: { Authorization: getTeacherBasicAuthHeaderValue() },
        body: JSON.stringify({
          student_id: numericStudentId,
          course: studyPlan?.course,
          topic_id: studyPlan?.topic_id,
          question_ids: cleanIds,
          finalize: options?.finalize ?? true,
        }),
      },
    )
  } catch {
    // Best-effort: study can continue if central is unreachable.
  }
}

function getDayRunIdFromStorage(): string {
  try {
    return window.sessionStorage.getItem('study:dayRunId') ?? ''
  } catch {
    return ''
  }
}

export const studentStudyGuideApi = {
  async createRun(input: CreateStudyRunRequest): Promise<CreateStudyRunResponse> {
    if (CENTRAL_API_BASE_URL) {
      let assessmentIdNum = Number(input.assessmentId)
      if (Number.isNaN(assessmentIdNum)) {
        // Fallback for flows that pass a non-numeric placeholder assessment id.
        // Resolve to the first available central assessment so session creation
        // does not fail with a FastAPI 422 (assessment_id=null).
        const assessments = await httpJson<
          Array<{ id: number; title: string; total_sessions: number; unreviewed_sessions: number }>
        >(`${CENTRAL_API_BASE_URL}/assessments`)
        if (!assessments.length) {
          throw new Error(
            `Invalid assessment id: ${input.assessmentId}. No assessments found in central backend.`,
          )
        }
        assessmentIdNum = assessments[0].id
      }

      const device_info: Record<string, unknown> = {
        source: 'web-student-ui',
        mode: 'study',
      }
      if (input.studyPlan) {
        const numericStudentId = input.studentId ? Number(input.studentId) : undefined
        device_info.study_plan = {
          ...input.studyPlan,
          ...(numericStudentId && numericStudentId > 0 ? { student_id: numericStudentId } : {}),
        }
      }

      const centralSession = await httpJson<{ id: string }>(`${CENTRAL_API_BASE_URL}/sessions`, {
        method: 'POST',
        headers: { Authorization: getTeacherBasicAuthHeaderValue() },
        body: JSON.stringify({
          assessment_id: assessmentIdNum,
          student_id:
            input.studentId && Number(input.studentId) > 0 ? Number(input.studentId) : null,
          device_info,
        }),
      })

      const sessionId = centralSession.id

      const jetsonBody: Record<string, unknown> = {
        session_id: sessionId,
        student_id: input.studentId ?? null,
        day_run_id: input.dayRunId ?? null,
        study_plan: input.studyPlan ?? null,
      }
      if (input.practiceQuestions && input.practiceQuestions.length > 0) {
        jetsonBody.practice_questions = input.practiceQuestions.map((q) => ({
          id: q.id,
          text: q.text,
          rubric_items: q.rubric_items,
          difficulty: q.difficulty,
          hints: q.hints ?? [],
        }))
        try {
          window.sessionStorage.setItem(practiceStorageKey(sessionId), JSON.stringify(input.practiceQuestions))
          if (input.studyPlan) {
            const numericStudentId = input.studentId ? Number(input.studentId) : undefined
            window.sessionStorage.setItem(
              studyPlanStorageKey(sessionId),
              JSON.stringify({
                ...input.studyPlan,
                ...(numericStudentId && numericStudentId > 0
                  ? { student_id: numericStudentId }
                  : {}),
              }),
            )
          }
        } catch {
          // ignore
        }
      } else {
        const examConfigResp = await httpJson<{ exam_config: unknown }>(
          `${CENTRAL_API_BASE_URL}/assessments/${encodeURIComponent(String(assessmentIdNum))}/exam-config`,
        )
        const cfg = examConfigResp.exam_config as { questions?: unknown[] } | null | undefined
        const questions = Array.isArray(cfg?.questions) ? cfg?.questions : []
        if (!cfg || questions.length === 0) {
          throw new Error('This assessment has no exam config available (missing questions).')
        }
        jetsonBody.exam_config = examConfigResp.exam_config
      }

      await httpJson<unknown>(`${JETSON_API_BASE_URL}/jetson/study-guide/runs`, {
        method: 'POST',
        body: JSON.stringify(jetsonBody),
      })
      return { sessionId }
    }

    const sessionId = `study-${Math.random().toString(16).slice(2)}`
    await httpJson<unknown>(`${JETSON_API_BASE_URL}/jetson/study-guide/runs`, {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
        student_id: input.studentId ?? null,
        day_run_id: input.dayRunId ?? null,
        study_plan: input.studyPlan ?? null,
        question_text:
          'A dataset has 200 students. 80 took CS109, 60 took CS111, and 30 took both. What is P(CS109 | CS111)? Show your work.',
        rubric_items: [
          'Uses the definition P(A|B) = P(A and B) / P(B)',
          'Correctly identifies counts for intersection and conditioning event from the prompt',
          'Computes P(CS109 | CS111) = 30/60 = 0.5',
          'Includes intermediate steps (not just the final number)',
        ],
      }),
    })
    return { sessionId }
  },

  async getState(sessionId: string): Promise<StudyRunState> {
    const state = await httpJson<BackendStudyState>(
      `${JETSON_API_BASE_URL}/jetson/study-guide/runs/${encodeURIComponent(sessionId)}/state`,
    )
    return {
      sessionId: state.session_id,
      status: state.status,
      questionText: state.questionText,
      feedbackMarkdown: state.feedbackMarkdown,
      followUpMarkdown: state.followUpMarkdown,
      latestImageUrl: state.latestImageUrl,
      error: state.error,
      captureCount: state.captureCount ?? 0,
      captureLimit: state.captureLimit ?? 5,
      questionIndex: state.questionIndex ?? 1,
      questionCount: state.questionCount ?? 1,
      hints: state.hints ?? [],
      amaTurns: (state.ama_turns ?? []).map((t) => ({ role: t.role, content: t.content })),
      answerMode: state.answerMode === 'oral' ? 'oral' : 'paper',
      oralTranscript: state.oralTranscript ?? '',
      oralHasRecording: Boolean(state.oralHasRecording),
    }
  },

  async setAnswerMode(sessionId: string, mode: StudyAnswerMode): Promise<void> {
    await httpJson<unknown>(
      `${JETSON_API_BASE_URL}/jetson/study-guide/runs/${encodeURIComponent(sessionId)}/answer-mode`,
      {
        method: 'POST',
        body: JSON.stringify({ mode }),
      },
    )
  },

  async uploadOralAnswer(sessionId: string, audio: Blob): Promise<void> {
    const form = new FormData()
    const ext = audio.type.includes('mp4') ? 'm4a' : audio.type.includes('wav') ? 'wav' : 'webm'
    form.append('audio', audio, `answer.${ext}`)
    const res = await fetch(
      `${JETSON_API_BASE_URL}/jetson/study-guide/runs/${encodeURIComponent(sessionId)}/oral-upload`,
      { method: 'POST', body: form },
    )
    if (!res.ok) {
      const err = new Error(`Request failed: ${res.status} ${res.statusText}`)
      ;(err as Error & { status?: number }).status = res.status
      throw err
    }
  },

  async retakeOral(sessionId: string): Promise<void> {
    await httpJson<unknown>(
      `${JETSON_API_BASE_URL}/jetson/study-guide/runs/${encodeURIComponent(sessionId)}/retake-oral`,
      { method: 'POST', body: JSON.stringify({}) },
    )
  },

  getStoredPracticeQuestions(sessionId: string): PracticeQuestionPayload[] | null {
    try {
      const raw = window.sessionStorage.getItem(practiceStorageKey(sessionId))
      if (!raw) return null
      return JSON.parse(raw) as PracticeQuestionPayload[]
    } catch {
      return null
    }
  },

  getStoredStudyPlan(sessionId: string): StudyPlanDeviceInfo | null {
    return readStoredStudyPlan(sessionId)
  },

  getCurrentPracticeQuestionId(sessionId: string, questionIndex: number): string | null {
    const practice = this.getStoredPracticeQuestions(sessionId)
    if (!practice?.length) return null
    const idx = Math.max(0, questionIndex - 1)
    return practice[idx]?.id?.trim() || null
  },

  async ensureRun(sessionId: string, assessmentId: string): Promise<void> {
    if (!CENTRAL_API_BASE_URL) {
      return
    }
    const dayRunId = getDayRunIdFromStorage()
    let studentId = ''
    try {
      studentId = window.sessionStorage.getItem(`study:studentId:${sessionId}`) ?? window.sessionStorage.getItem('study:studentId') ?? ''
    } catch {
      studentId = ''
    }
    let stored: string | null = null
    try {
      stored = window.sessionStorage.getItem(practiceStorageKey(sessionId))
    } catch {
      stored = null
    }
    if (stored) {
      try {
        const practiceQuestions = JSON.parse(stored) as PracticeQuestionPayload[]
        await httpJson<unknown>(`${JETSON_API_BASE_URL}/jetson/study-guide/runs`, {
          method: 'POST',
          body: JSON.stringify({
            session_id: sessionId,
            student_id: studentId || null,
            day_run_id: dayRunId || null,
            practice_questions: practiceQuestions,
          }),
        })
        return
      } catch {
        // fall through to exam_config recovery
      }
    }
    const examConfigResp = await httpJson<{ exam_config: unknown }>(
      `${CENTRAL_API_BASE_URL}/assessments/${encodeURIComponent(assessmentId)}/exam-config`,
    )
    const cfg = examConfigResp.exam_config as { questions?: unknown[] } | null | undefined
    const questions = Array.isArray(cfg?.questions) ? cfg?.questions : []
    if (!cfg || questions.length === 0) {
      throw new Error('This assessment has no exam config available (missing questions).')
    }
    await httpJson<unknown>(`${JETSON_API_BASE_URL}/jetson/study-guide/runs`, {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
        student_id: studentId || null,
        day_run_id: dayRunId || null,
        exam_config: examConfigResp.exam_config,
      }),
    })
  },

  async nextQuestion(sessionId: string, completedQuestionId?: string): Promise<void> {
    if (completedQuestionId?.trim()) {
      addStoredCompletedQuestionId(sessionId, completedQuestionId)
      await recordStudySeenToCentral(sessionId, [completedQuestionId], { finalize: false })
    }
    await httpJson<unknown>(
      `${JETSON_API_BASE_URL}/jetson/study-guide/runs/${encodeURIComponent(sessionId)}/next-question`,
      { method: 'POST', body: JSON.stringify({}) },
    )
  },

  async capture(sessionId: string): Promise<void> {
    await httpJson<unknown>(`${JETSON_API_BASE_URL}/jetson/study-guide/runs/${encodeURIComponent(sessionId)}/capture`, {
      method: 'POST',
      body: JSON.stringify({ width: 1280, height: 720 }),
    })
  },

  /**
   * Send a JPEG from the browser (same frame as the live preview).
   * Use this on the Jetson while Firefox holds /dev/video0 so the server does not open the camera.
   */
  async captureUpload(sessionId: string, imageBlob: Blob): Promise<void> {
    const fd = new FormData()
    fd.append('image', imageBlob, 'paper.jpg')
    const res = await fetch(
      `${JETSON_API_BASE_URL}/jetson/study-guide/runs/${encodeURIComponent(sessionId)}/capture-upload`,
      {
        method: 'POST',
        body: fd,
      },
    )
    if (!res.ok) {
      const err = new Error(`Request failed: ${res.status} ${res.statusText}`)
      ;(err as Error & { status?: number }).status = res.status
      throw err
    }
    await res.json()
  },

  async retakeLast(sessionId: string): Promise<{ captureCount: number; captureLimit: number }> {
    const res = await fetch(
      `${JETSON_API_BASE_URL}/jetson/study-guide/runs/${encodeURIComponent(sessionId)}/retake-last`,
      { method: 'POST' },
    )
    if (!res.ok) {
      const err = new Error(`Request failed: ${res.status} ${res.statusText}`)
      ;(err as Error & { status?: number }).status = res.status
      throw err
    }
    const body = (await res.json()) as { captureCount?: number; captureLimit?: number }
    return { captureCount: body.captureCount ?? 0, captureLimit: body.captureLimit ?? 5 }
  },

  async grade(sessionId: string): Promise<void> {
    await httpJson<unknown>(`${JETSON_API_BASE_URL}/jetson/study-guide/runs/${encodeURIComponent(sessionId)}/grade`, {
      method: 'POST',
      body: JSON.stringify({}),
    })
  },

  async actionUnderstand(sessionId: string): Promise<void> {
    await httpJson<unknown>(`${JETSON_API_BASE_URL}/jetson/study-guide/runs/${encodeURIComponent(sessionId)}/action`, {
      method: 'POST',
      body: JSON.stringify({ action: 'understand' }),
    })
  },

  async actionLost(sessionId: string): Promise<void> {
    await httpJson<unknown>(`${JETSON_API_BASE_URL}/jetson/study-guide/runs/${encodeURIComponent(sessionId)}/action`, {
      method: 'POST',
      body: JSON.stringify({ action: 'lost' }),
    })
  },

  async actionQuestion(sessionId: string, questionText: string): Promise<void> {
    await httpJson<unknown>(`${JETSON_API_BASE_URL}/jetson/study-guide/runs/${encodeURIComponent(sessionId)}/action`, {
      method: 'POST',
      body: JSON.stringify({ action: 'question', questionText }),
    })
  },

  /** Full-session-context tutor chat (Ask me anything). */
  async actionAma(sessionId: string, questionText: string): Promise<{ reply: string }> {
    return httpJson<{ status: string; reply: string }>(
      `${JETSON_API_BASE_URL}/jetson/study-guide/runs/${encodeURIComponent(sessionId)}/action`,
      {
        method: 'POST',
        body: JSON.stringify({ action: 'ama', questionText }),
      },
    )
  },

  async endRun(sessionId: string, completedQuestionId?: string): Promise<void> {
    await httpJson<unknown>(
      `${JETSON_API_BASE_URL}/jetson/study-guide/runs/${encodeURIComponent(sessionId)}/end`,
      {
        method: 'POST',
        body: JSON.stringify({}),
      },
    )
    const completedIds = [...getStoredCompletedQuestionIds(sessionId)]
    if (completedQuestionId?.trim() && !completedIds.includes(completedQuestionId.trim())) {
      completedIds.push(completedQuestionId.trim())
      addStoredCompletedQuestionId(sessionId, completedQuestionId)
    }
    await recordStudySeenToCentral(sessionId, completedIds, { finalize: true })
  },

  async getStudySurveyStatus(studentId: string): Promise<{ completed: boolean }> {
    if (!CENTRAL_API_BASE_URL) {
      throw new Error('Central API base URL is not configured')
    }
    const resp = await httpJson<{ student_id: number; completed: boolean }>(
      `${CENTRAL_API_BASE_URL}/sessions/study-survey-status?student_id=${encodeURIComponent(studentId)}`,
    )
    return { completed: resp.completed }
  },

  async markStudySurveyCompleted(sessionId: string, options?: { skipped?: boolean }): Promise<void> {
    if (!CENTRAL_API_BASE_URL) {
      throw new Error('Central API base URL is not configured')
    }
    await httpJson<unknown>(
      `${CENTRAL_API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}/study-survey-completed`,
      {
        method: 'POST',
        body: JSON.stringify({ skipped: Boolean(options?.skipped) }),
      },
    )
  },

  /**
   * Submit the optional end-of-study exit survey.
   *
   * The Jetson endpoint accepts any subset of the survey fields; the caller
   * (``StudentExitSurveyPage``) is responsible for short-circuiting the
   * POST entirely when all fields are empty. Errors are propagated so the
   * page can decide to swallow them and still navigate onward.
   */
  async submitExitSurvey(
    sessionId: string,
    body: {
      helpfulness: number | null
      ease_of_use: number | null
      question_difficulty: number | null
      would_use_again: boolean | null
      liked: string
      disliked: string
      improvements: string
      anything_else: string
      response_feedback: string
    },
  ): Promise<void> {
    await httpJson<unknown>(
      `${JETSON_API_BASE_URL}/jetson/study-guide/runs/${encodeURIComponent(sessionId)}/survey`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      },
    )
  },

  /**
   * Best-effort client-side telemetry (tab switching, unload, client errors).
   * Uses sendBeacon when requested/available so it can fire during page unload.
   */
  async logClientEvent(
    sessionId: string,
    body: {
      type: string
      question_index?: number | null
      data?: Record<string, unknown>
      client_ts_ms?: number | null
    },
    opts?: { preferBeacon?: boolean },
  ): Promise<void> {
    const payload = {
      ...body,
      client_ts_ms: body.client_ts_ms ?? Date.now(),
      data: body.data ?? {},
    }
    const url = `${JETSON_API_BASE_URL}/jetson/study-guide/runs/${encodeURIComponent(sessionId)}/client-event`

    if (opts?.preferBeacon && typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
      try {
        const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' })
        navigator.sendBeacon(url, blob)
        return
      } catch {
        // fall through to fetch
      }
    }

    try {
      await fetch(url, {
        method: 'POST',
        body: JSON.stringify(payload),
        headers: { 'content-type': 'application/json' },
        keepalive: Boolean(opts?.preferBeacon),
      })
    } catch {
      // ignore telemetry failures
    }
  },
}
