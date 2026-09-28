import { Link } from 'react-router-dom'

import { ROUTE_PATH } from '../routes/paths'
import styles from './TeacherFeedbackSubmittedPage.module.css'

export function TeacherFeedbackSubmittedPage() {
  return (
    <main className={styles.page}>
      <h1 className={styles.title}>Feedback Submitted</h1>
      <p className={styles.subtitle}>Thanks for sharing your feedback.</p>
      <Link className={styles.linkButton} to={ROUTE_PATH.TEACHER_HOME}>
        Go Back to Home Page
      </Link>
    </main>
  )
}
