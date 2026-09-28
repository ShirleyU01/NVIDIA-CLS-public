import { Link } from 'react-router-dom'

import { ROUTE_PATH } from '../routes/paths'
import styles from './StudentDonePage.module.css'

export function StudentDonePage() {
  return (
    <main className={styles.page}>
      <h1 className={styles.title}>Your Exam Is Complete</h1>
      <p className={styles.subtitle}>
        Your responses and recordings have been saved. Your instructor will review them and provide
        feedback later.
      </p>
      <Link className={styles.linkButton} to={ROUTE_PATH.STUDENT_HOME} data-tour="student-done-home">
        Go Back to Home Page
      </Link>
    </main>
  )
}
