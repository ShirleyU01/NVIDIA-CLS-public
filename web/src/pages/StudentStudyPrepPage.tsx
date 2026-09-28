import { useLocation, useNavigate } from 'react-router-dom'

import { buildTimeOfDayGreeting } from '../utils/greeting'
import { ROUTE_PATH } from '../routes/paths'
import styles from './StudentStudyPrepPage.module.css'

export function StudentStudyPrepPage() {
  const greeting = buildTimeOfDayGreeting(new Date(), 'Student')
  const navigate = useNavigate()
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  const assessmentIdFromQuery = params.get('assessmentId') ?? ''
  const assessmentQuery = assessmentIdFromQuery
    ? `?assessmentId=${encodeURIComponent(assessmentIdFromQuery)}`
    : ''

  const handleBeginStudy = async () => {
    navigate(`${ROUTE_PATH.STUDENT_STUDY_ID}${assessmentQuery}`)
  }

  return (
    <main className={styles.page}>
      <p className={styles.greeting}>{greeting}</p>
      <p className={styles.headline}>Pre-prep Practice</p>

      <section className={styles.topics} aria-label="Study Guide Instructions">
        <article className={styles.topicCard}>
          <h2>How Study Mode Works</h2>
          <ul>
            <li>For each question, choose how to answer: <strong>write on paper</strong> or <strong>speak</strong> into the microphone.</li>
            <li>On paper: show your work to the camera and capture your page(s).</li>
            <li>By voice: record your explanation, then we transcribe and evaluate what you said.</li>
            <li>The system gives step-by-step feedback either way.</li>
          </ul>
        </article>

        <article className={styles.topicCard}>
          <h2>Tips for a Good Photo</h2>
          <ul>
            <li>Fill the frame with the paper (big, readable writing).</li>
            <li>Use bright lighting; avoid glare and shadows.</li>
            <li>Hold the page steady when you tap capture.</li>
          </ul>
        </article>
      </section>

      <button
        className={styles.beginButton}
        type="button"
        data-tour="student-begin-study"
        onClick={handleBeginStudy}
      >
        Begin Study
      </button>
    </main>
  )
}
