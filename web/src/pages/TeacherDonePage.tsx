import { Link } from 'react-router-dom'

import { ROUTE_PATH } from '../routes/paths'
import styles from './TeacherDonePage.module.css'

export function TeacherDonePage() {
  return (
    <main className={styles.page}>
      <h1 className={styles.title}>Review Complete</h1>
      <p className={styles.subtitle}>
        Your decision and any overrides have been recorded for this session.
      </p>
      <Link className={styles.linkButton} to={ROUTE_PATH.TEACHER_REVIEW}>
        Return to Review
      </Link>
    </main>
  )
}
