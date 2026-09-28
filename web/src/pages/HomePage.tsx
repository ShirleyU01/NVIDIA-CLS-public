import { Link } from 'react-router-dom'

import { buildTimeOfDayGreeting } from '../utils/greeting'
import { ROUTE_PATH } from '../routes/paths'
import styles from './HomePage.module.css'

export function HomePage() {
  const greeting = buildTimeOfDayGreeting(new Date(), 'Instructor')

  return (
    <main className={styles.page}>
      <header className={styles.centeredHeader}>
        <p className={styles.greeting}>{greeting}</p>
        <h1 className={styles.headline}>Teacher Console</h1>
        <p className={styles.subHeadline}>What would you like to do today?</p>
      </header>

      <section className={styles.mainActions} aria-label="Teacher Main Actions">
        <Link className={styles.primaryAction} to={ROUTE_PATH.TEACHER_ASSESSMENTS}>
          <span className={styles.actionTitle}>View Past Exams</span>
          <span className={styles.actionBody}>
            Browse all published assessments and drill into sessions and scores.
          </span>
        </Link>

        <Link className={styles.secondaryAction} to={ROUTE_PATH.TEACHER_CREATE_EXAM}>
          <span className={styles.actionTitle}>Create New Exam</span>
          <span className={styles.actionBody}>
            Define questions and rubric criteria to generate a new assessment.
          </span>
        </Link>

        <Link className={styles.secondaryAction} to={ROUTE_PATH.TEACHER_STUDY_DASHBOARD}>
          <span className={styles.actionTitle}>Study Mode Dashboard</span>
          <span className={styles.actionBody}>
            Review Study Mode completion, feedback latency, survey ratings, and topic trends.
          </span>
        </Link>
      </section>
    </main>
  )
}
