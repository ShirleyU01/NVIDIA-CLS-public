import { Link } from 'react-router-dom'
import { useEffect, useState } from 'react'

import { teacherApi } from '../api/teacher'
import type { AssessmentSummary } from '../types/assessment'
import { ROUTE_PATH } from '../routes/paths'
import styles from './TeacherAssessmentsPage.module.css'

export function TeacherAssessmentsPage() {
  const [assessments, setAssessments] = useState<AssessmentSummary[]>([])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const data = await teacherApi.getAssessments()
        if (!cancelled) setAssessments(data)
      } catch {
        // ignore errors for now; empty list is fine
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Past Exams</h1>
        <p className={styles.subtitle}>Browse published assessments and their sessions.</p>
      </header>

      <section aria-label="Assessments List" className={styles.tableWrapper}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Assessment</th>
              <th scope="col">Total sessions</th>
              <th scope="col">Unreviewed sessions</th>
              <th scope="col" aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {assessments.map((assessment) => (
              <tr key={assessment.id}>
                <td>{assessment.title}</td>
                <td>{assessment.totalSessions}</td>
                <td>{assessment.unreviewedSessions}</td>
                <td className={styles.actionsCell}>
                  <Link
                    className={styles.linkButton}
                    to={ROUTE_PATH.TEACHER_ASSESSMENTS + '/' + encodeURIComponent(assessment.id)}
                  >
                    View
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  )
}
