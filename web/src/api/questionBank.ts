const CENTRAL_API_BASE_URL = import.meta.env.VITE_CENTRAL_API_BASE_URL

async function httpJson<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const res = await fetch(input, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    const err = new Error(`Request failed: ${res.status} ${res.statusText}`)
    ;(err as Error & { status?: number }).status = res.status
    throw err
  }
  return (await res.json()) as T
}

export interface QuestionBankCourse {
  id: string
  title: string
}

export interface QuestionBankTopic {
  id: string
  name: string
}

export interface PracticeQuestionPayload {
  id: string
  text: string
  rubric_items: string[]
  difficulty?: string
  hints?: string[]
}

export const questionBankApi = {
  async listCourses(): Promise<QuestionBankCourse[]> {
    if (!CENTRAL_API_BASE_URL) return []
    return httpJson<QuestionBankCourse[]>(`${CENTRAL_API_BASE_URL}/question-bank/courses`)
  },

  async listTopics(courseId: string): Promise<QuestionBankTopic[]> {
    if (!CENTRAL_API_BASE_URL) return []
    return httpJson<QuestionBankTopic[]>(
      `${CENTRAL_API_BASE_URL}/question-bank/courses/${encodeURIComponent(courseId)}/topics`,
    )
  },

  async selectQuestions(
    courseId: string,
    topicId: string,
    count: number,
    studentId?: string,
    seed?: number,
  ): Promise<PracticeQuestionPayload[]> {
    if (!CENTRAL_API_BASE_URL) {
      throw new Error('Central API is not configured (VITE_CENTRAL_API_BASE_URL).')
    }
    const body: { topic_id: string; count: number; student_id?: number; seed?: number } = { topic_id: topicId, count }
    if (studentId) body.student_id = Number(studentId)
    if (seed !== undefined) body.seed = seed
    const resp = await httpJson<{ questions: PracticeQuestionPayload[] }>(
      `${CENTRAL_API_BASE_URL}/question-bank/courses/${encodeURIComponent(courseId)}/selection`,
      { method: 'POST', body: JSON.stringify(body) },
    )
    return resp.questions ?? []
  },

  async listSeenQuestions(
    courseId: string,
    studentId: string,
    topicId?: string,
  ): Promise<PracticeQuestionPayload[]> {
    if (!CENTRAL_API_BASE_URL) {
      throw new Error('Central API is not configured (VITE_CENTRAL_API_BASE_URL).')
    }
    const params = new URLSearchParams({ student_id: studentId })
    if (topicId) params.set('topic_id', topicId)
    const resp = await httpJson<{ questions: PracticeQuestionPayload[] }>(
      `${CENTRAL_API_BASE_URL}/question-bank/courses/${encodeURIComponent(courseId)}/seen?${params.toString()}`,
    )
    return resp.questions ?? []
  },
}
