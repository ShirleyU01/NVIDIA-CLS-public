import { useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'

import { studentExamApi } from '../api/studentExam'
import { teacherApi } from '../api/teacher'
import { isTeacherAuthed, setTeacherAuthed, validateTeacherCredentials } from '../auth/teacherAuth'
import { buildTimeOfDayGreeting } from '../utils/greeting'
import { ROUTE_PATH } from '../routes/paths'
import styles from './StudentPrepPage.module.css'

export function StudentPrepPage() {
  const greeting = buildTimeOfDayGreeting(new Date(), 'Student')
  const navigate = useNavigate()
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  const assessmentId = params.get('assessmentId') ?? 'demo-bayes-oral-exam'
  const [title, setTitle] = useState("Bayes' Rule Oral Exam")
  const [authOpen, setAuthOpen] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [authError, setAuthError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)

  useEffect(() => {
    let cancelled = false
    const loadTitle = async () => {
      try {
        const assessments = await teacherApi.getAssessments()
        const match = assessments.find((a) => String(a.id) === assessmentId)
        if (!cancelled && match) setTitle(match.title)
      } catch {
        // ignore; keep default title
      }
    }
    void loadTitle()
    return () => {
      cancelled = true
    }
  }, [assessmentId])

  const startExam = async () => {
    setStarting(true)
    try {
      const { sessionId } = await studentExamApi.createSession({
        assessmentId,
      })
      navigate(`${ROUTE_PATH.STUDENT_SESSION}?sessionId=${encodeURIComponent(sessionId)}`)
    } finally {
      setStarting(false)
    }
  }

  const handleBeginExam = async () => {
    if (!isTeacherAuthed()) {
      setAuthOpen(true)
      setAuthError(null)
      setUsername('')
      setPassword('')
      return
    }
    await startExam()
  }

  const handleAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!validateTeacherCredentials(username.trim(), password)) {
      setTeacherAuthed(false)
      setAuthError('Invalid username or password.')
      return
    }
    setTeacherAuthed(true)
    setAuthOpen(false)
    setAuthError(null)
    await startExam()
  }

  return (
    <main className={styles.page}>
      <p className={styles.greeting}>{greeting}</p>
      <p className={styles.headline}>{title}</p>

      <section className={styles.topics} aria-label="Exam Instructions">
        <article className={styles.topicCard}>
          <h2>Before You Begin</h2>
          <ul>
            <li>Make sure you are in a quiet place.</li>
            <li>Keep your camera pointed at your face during the exam.</li>
            <li>Speak clearly; pauses are okay.</li>
          </ul>
        </article>

        <article className={styles.topicCard}>
          <h2>What to Expect</h2>
          <ul>
            <li>Your instructor has prepared several questions about Bayes&apos; Rule.</li>
            <li>The system will listen, think, and sometimes ask follow-up questions.</li>
            <li>
              When the exam ends, your instructor will review an evidence packet with scores and
              quotes.
            </li>
          </ul>
        </article>
      </section>

      {authOpen ? (
        <section aria-label="Teacher authentication" style={{ marginTop: 20, maxWidth: 420 }}>
          <h2 style={{ margin: '0 0 8px' }}>Teacher check</h2>
          <p style={{ margin: '0 0 12px', opacity: 0.85 }}>
            Only instructors can start a new exam session.
          </p>
          <form onSubmit={handleAuthSubmit}>
            <label style={{ display: 'block', marginBottom: 10 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Username</div>
              <input
                name="username"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                style={{ width: '100%', padding: '10px 12px' }}
              />
            </label>
            <label style={{ display: 'block', marginBottom: 10 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Password</div>
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={{ width: '100%', padding: '10px 12px' }}
              />
            </label>
            {authError ? (
              <div role="alert" style={{ color: '#b00020', marginBottom: 10 }}>
                {authError}
              </div>
            ) : null}
            <div style={{ display: 'flex', gap: 10 }}>
              <button type="submit" className={styles.beginButton} disabled={starting}>
                Start exam
              </button>
              <button
                type="button"
                className={styles.beginButton}
                style={{ opacity: 0.85 }}
                onClick={() => setAuthOpen(false)}
                disabled={starting}
              >
                Cancel
              </button>
            </div>
          </form>
        </section>
      ) : null}

      <button
        className={styles.beginButton}
        type="button"
        data-tour="student-begin-exam"
        onClick={handleBeginExam}
        disabled={starting}
      >
        {starting ? 'Starting…' : 'Begin Exam'}
      </button>
    </main>
  )
}
