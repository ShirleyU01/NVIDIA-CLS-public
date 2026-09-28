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

export const studentsApi = {
  /**
   * Register this numeric ID on first sign-in (no roster required).
   */
  async ensureRegistered(studentId: string): Promise<void> {
    if (!CENTRAL_API_BASE_URL) {
      return
    }
    const numericId = Number(studentId)
    if (!Number.isFinite(numericId) || numericId <= 0) {
      throw new Error('Enter a valid numeric student ID.')
    }
    await httpJson<{ student_id: number; status: string }>(
      `${CENTRAL_API_BASE_URL}/students/ensure`,
      {
        method: 'POST',
        body: JSON.stringify({ student_id: numericId }),
      },
    )
  },
}
