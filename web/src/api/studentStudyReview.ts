import type { StudyStudentFeedbackAny } from '../types/studyFeedback'

/**
 * Polling adapter for the student study review page.
 *
 * Hits the central backend's ``GET /sessions/:id`` endpoint and collapses
 * the response down to the only field the review page actually needs:
 * ``study_feedback``. While the Jetson ``/end`` endpoint is still running
 * (or central just hasn't received the artifact yet) the field will be
 * absent and we report ``status: 'pending'`` so the UI can keep polling.
 */

const CENTRAL_API_BASE_URL = import.meta.env.VITE_CENTRAL_API_BASE_URL

export interface StudyReview {
  status: 'pending' | 'ready'
  feedback: StudyStudentFeedbackAny | null
}

interface StudySessionPayload {
  study_feedback?: StudyStudentFeedbackAny | null
}

function isReadyFeedback(raw: unknown): raw is StudyStudentFeedbackAny {
  if (!raw || typeof raw !== 'object') return false
  const o = raw as Record<string, unknown>
  return (
    Array.isArray(o.high_level_takeaways) &&
    Array.isArray(o.areas_to_improve) &&
    Array.isArray(o.next_steps)
  )
}

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

/**
 * Fetch the study review payload for ``sessionId``.
 *
 * Returns ``{ status: 'ready', feedback }`` once the Jetson's end-of-study
 * artifacts have made it into central; otherwise ``{ status: 'pending', feedback: null }``.
 *
 * If ``CENTRAL_API_BASE_URL`` isn't configured (dev mode without central),
 * we surface a stable pending state so the polling loop never crashes.
 */
export async function getStudentStudyReview(sessionId: string): Promise<StudyReview> {
  if (!CENTRAL_API_BASE_URL) {
    return { status: 'pending', feedback: null }
  }
  const payload = await httpJson<StudySessionPayload>(
    `${CENTRAL_API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}`,
  )
  const feedback = payload.study_feedback
  if (!isReadyFeedback(feedback)) {
    return { status: 'pending', feedback: null }
  }
  return { status: 'ready', feedback }
}
