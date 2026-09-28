import { useState } from 'react'
import { Link } from 'react-router-dom'

import { buildTimeOfDayGreeting } from '../utils/greeting'
import { ROUTE_PATH } from '../routes/paths'
import styles from './TeacherFeedbackPage.module.css'

export function TeacherFeedbackPage() {
  const [feedback, setFeedback] = useState('')
  const greeting = buildTimeOfDayGreeting(new Date(), 'Instructor')

  return (
    <main className={styles.page}>
      <p className={styles.greeting}>{greeting}</p>
      <h1 className={styles.title}>Optional Feedback for the Team</h1>

      <section className={styles.feedback}>
        <label htmlFor="teacher-feedback-text">
          Is there anything we should improve about this exam or the automated grading?
        </label>
        <textarea
          id="teacher-feedback-text"
          name="teacher-feedback-text"
          rows={6}
          value={feedback}
          onChange={(event) => setFeedback(event.target.value)}
          placeholder="Add notes for the team..."
        />
      </section>

      <Link to={ROUTE_PATH.TEACHER_FEEDBACK_SUBMITTED}>
        <button type="button" className={styles.doneButton}>
          Submit Feedback
        </button>
      </Link>
    </main>
  )
}
