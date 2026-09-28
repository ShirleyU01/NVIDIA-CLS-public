import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { teacherApi } from '../api/teacher'
import type { AssessmentSummary } from '../types/assessment'
import { ROUTE_PATH } from '../routes/paths'
import styles from './StudentAssessmentsPage.module.css'

export function StudentAssessmentsPage() {
  const [assessments, setAssessments] = useState<AssessmentSummary[]>([])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const data = await teacherApi.getAssessments()
        if (!cancelled) setAssessments(data)
      } catch {
        // ignore errors for now; an empty list is fine in dev
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
        <h1 className={styles.title}>Available Exams</h1>
        <p className={styles.subtitle}>Choose an exam to begin the oral assessment.</p>
      </header>

      <section className={styles.tableWrapper} aria-label="Available Assessments">
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Exam</th>
              <th scope="col">Total sessions</th>
              <th scope="col">Unreviewed</th>
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
                  <div className={styles.actionGroup}>
                    <Link
                      className={styles.linkButton}
                      data-tour="student-study-default"
                      to={`${ROUTE_PATH.STUDENT_STUDY_PREP}?assessmentId=${encodeURIComponent(assessment.id)}`}
                    >
                      Study (default)
                    </Link>
                    <Link
                      className={styles.linkButtonSecondary}
                      data-tour="student-exam-mode"
                      to={`${ROUTE_PATH.STUDENT_PREP}?assessmentId=${encodeURIComponent(assessment.id)}`}
                    >
                      Exam mode
                    </Link>
                  </div>
                </td>
              </tr>
            ))}
            {assessments.length === 0 ? (
              <tr>
                <td colSpan={4} className={styles.emptyCell}>
                  No Exams Available Yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </main>
  )
}
