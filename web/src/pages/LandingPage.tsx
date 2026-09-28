import { Link } from 'react-router-dom'

import { ROUTE_PATH } from '../routes/paths'
import styles from './LandingPage.module.css'

export function LandingPage() {
  return (
    <main className={styles.page}>
      <header className={styles.centeredHeader}>
        <p className={styles.kicker}>Socrates</p>
        <h1 className={styles.headline}>Welcome</h1>
        <p className={styles.subHeadline}>Choose how you want to enter the platform.</p>
      </header>

      <section className={styles.mainActions} aria-label="Role Selection">
        <Link className={styles.primaryAction} to={ROUTE_PATH.STUDENT_HOME}>
          I&apos;m a student
        </Link>
        <Link className={styles.secondaryAction} to={ROUTE_PATH.TEACHER_HOME}>
          I&apos;m a teacher
        </Link>
      </section>
    </main>
  )
}
