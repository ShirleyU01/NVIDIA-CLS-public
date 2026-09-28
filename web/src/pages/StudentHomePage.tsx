import { Link, useNavigate } from 'react-router-dom'
import { useState } from 'react'

import { ROUTE_PATH } from '../routes/paths'
import { setTeacherAuthed, validateTeacherCredentials } from '../auth/teacherAuth'
import { buildTimeOfDayGreeting } from '../utils/greeting'
import styles from './StudentHomePage.module.css'

export function StudentHomePage() {
  const greeting = buildTimeOfDayGreeting(new Date(), 'Student')
  const navigate = useNavigate()
  const [authOpen, setAuthOpen] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [authError, setAuthError] = useState<string | null>(null)

  const handleStartExamClick = () => {
    setAuthOpen(true)
    setUsername('')
    setPassword('')
    setAuthError(null)
  }

  const handleAuthSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!validateTeacherCredentials(username.trim(), password)) {
      setTeacherAuthed(false)
      setAuthError('Invalid username or password.')
      return
    }
    setTeacherAuthed(true)
    setAuthOpen(false)
    setAuthError(null)
    navigate(ROUTE_PATH.STUDENT_ASSESSMENTS)
  }

  return (
    <main className={styles.page}>
      <header className={styles.centeredHeader}>
        <p className={styles.greeting}>{greeting}</p>
        <h1 className={styles.headline}>Student Hub</h1>
        <p className={styles.subHeadline}>Choose exam mode or pre-prep practice.</p>
      </header>

      <section className={styles.mainActions} aria-label="Student Main Actions">
        <button className={styles.primaryAction} type="button" onClick={handleStartExamClick}>
          Start an Exam
        </button>
        <Link className={styles.secondaryAction} to={ROUTE_PATH.STUDENT_STUDY_PREP}>
          Pre-prep Practice
        </Link>
      </section>

      {authOpen ? (
        <section
          aria-label="Teacher authentication"
          style={{ marginTop: 18, maxWidth: 420, marginLeft: 'auto', marginRight: 'auto' }}
        >
          <h2 style={{ margin: '0 0 8px' }}>Teacher check</h2>
          <p style={{ margin: '0 0 12px', opacity: 0.85 }}>
            Only instructors can start a new exam.
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
              <button type="submit" className={styles.primaryAction}>
                Continue
              </button>
              <button type="button" className={styles.secondaryAction} onClick={() => setAuthOpen(false)}>
                Cancel
              </button>
            </div>
          </form>
        </section>
      ) : null}
    </main>
  )
}
