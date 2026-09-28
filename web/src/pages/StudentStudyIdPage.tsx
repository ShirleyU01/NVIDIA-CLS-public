import { useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { studentsApi } from '../api/students'
import { ROUTE_PATH } from '../routes/paths'
import styles from './StudentStudyIdPage.module.css'

function isValidStudentId(value: string): boolean {
  const trimmed = value.trim()
  if (!/^\d+$/.test(trimmed)) return false
  return Number(trimmed) > 0
}

export function StudentStudyIdPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  const assessmentId = params.get('assessmentId') ?? ''
  const [studentId, setStudentId] = useState(() => {
    try {
      return window.sessionStorage.getItem('study:studentId') ?? ''
    } catch {
      return ''
    }
  })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const trimmed = studentId.trim()
    if (!isValidStudentId(trimmed)) {
      setError('Enter a positive numeric student ID (for example, 2101).')
      return
    }

    setBusy(true)
    setError(null)
    try {
      await studentsApi.ensureRegistered(trimmed)

      try {
        window.sessionStorage.setItem('study:studentId', trimmed)
        // "Day run" groups multiple practice sessions under one visit/day so we
        // only show the exit survey once at the end.
        const existingDayRun = window.sessionStorage.getItem('study:dayRunId') ?? ''
        if (!existingDayRun) {
          const today = new Date()
          const yyyy = String(today.getFullYear())
          const mm = String(today.getMonth() + 1).padStart(2, '0')
          const dd = String(today.getDate()).padStart(2, '0')
          window.sessionStorage.setItem('study:dayRunId', `${yyyy}-${mm}-${dd}`)
        }
      } catch {
        // If storage is unavailable, keep going with the query-string value.
      }

      const next = new URLSearchParams()
      if (assessmentId) next.set('assessmentId', assessmentId)
      next.set('studentId', trimmed)
      navigate(`${ROUTE_PATH.STUDENT_STUDY_CONFIG}?${next.toString()}`)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Could not sign in. Check that the practice server is running and try again.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className={styles.page}>
      <section className={styles.card}>
        <p className={styles.kicker}>Study Mode</p>
        <h1 className={styles.title}>Sign in with your student ID</h1>
        <p className={styles.subtitle}>
          Enter any positive numeric ID (for example, 2101). First-time sign-in is
          fine — you do not need to be on a roster beforehand.
        </p>
        <form className={styles.form} onSubmit={handleSubmit} noValidate>
          <label className={styles.label} htmlFor="student-id">
            Student ID
          </label>
          <input
            id="student-id"
            className={styles.input}
            inputMode="numeric"
            pattern="[0-9]*"
            autoComplete="off"
            value={studentId}
            onChange={(e) => {
              setStudentId(e.target.value)
              setError(null)
            }}
          />
          {error ? (
            <p className={styles.error} role="alert">
              {error}
            </p>
          ) : null}
          <button type="submit" className={styles.button} disabled={busy}>
            {busy ? 'Signing in…' : 'Continue'}
          </button>
        </form>
      </section>
    </main>
  )
}
