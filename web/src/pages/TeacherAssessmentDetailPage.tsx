import { Link, useParams } from 'react-router-dom'
import { useEffect, useState } from 'react'

import { teacherApi } from '../api/teacher'
import type { AssessmentSessionsResponse, GradeBucket } from '../types/assessment'
import { ROUTE_PATH } from '../routes/paths'
import styles from './TeacherAssessmentDetailPage.module.css'

const formatStatusLabel = (value: string) =>
  value
    .split(/[_-\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')

/** Parse date from API as UTC when no timezone (backend sends naive UTC with Z in serializer; defensive for legacy). */
function parseSessionDate(value: string | Date | null | undefined): Date | null {
  if (value == null) return null
  if (typeof value === 'string') {
    const asUtc =
      value.endsWith('Z') || /[+-]\d{2}:?\d{2}$/.test(value) ? value : value + 'Z'
    const d = new Date(asUtc)
    return Number.isNaN(d.getTime()) ? null : d
  }
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

export function TeacherAssessmentDetailPage() {
  const { assessmentId } = useParams<{ assessmentId: string }>()
  const [data, setData] = useState<AssessmentSessionsResponse | null>(null)

  useEffect(() => {
    if (!assessmentId) return
    let cancelled = false
    const load = async () => {
      try {
        const result = await teacherApi.getAssessmentSessions(assessmentId)
        if (!cancelled) setData(result)
      } catch {
        // ignore for now
      }
    }
    void load()
    const intervalId = window.setInterval(load, 5000)
    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [assessmentId])

  const assessment = data?.assessment
  const sessions = data?.sessions ?? []
  const gradeBuckets: GradeBucket[] = data?.grade_buckets ?? []
  const totalGrades = gradeBuckets.reduce((sum, b) => sum + b.count, 0) || 1

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <p className={styles.breadcrumb}>
          <Link to={ROUTE_PATH.TEACHER_ASSESSMENTS} className={styles.breadcrumbLink}>
            Past Exams
          </Link>
          <span className={styles.breadcrumbSeparator}>/</span>
          <span>{assessment?.title ?? assessmentId}</span>
        </p>
        <h1 className={styles.title}>{assessment?.title ?? 'Loading...'}</h1>
        {assessment ? (
          <p className={styles.subtitle}>
            {formatStatusLabel(assessment.status)} · {sessions.length} Sessions
          </p>
        ) : null}
      </header>

      <section className={styles.gradeSection} aria-label="Grade Distribution">
        <h2 className={styles.sectionTitle}>Grade Distribution (Mock)</h2>
        <div className={styles.barChart}>
          {gradeBuckets.map((bucket) => {
            const pct = Math.round((bucket.count / totalGrades) * 100)
            return (
              <div key={bucket.label} className={styles.barRow}>
                <span className={styles.barLabel}>{bucket.label}</span>
                <div className={styles.barTrack}>
                  <div className={styles.barFill} style={{ width: `${pct}%` }} />
                </div>
                <span className={styles.barValue}>
                  {bucket.count} ({pct}%)
                </span>
              </div>
            )
          })}
        </div>
      </section>

      <section className={styles.tableWrapper} aria-label="Sessions for This Assessment">
        <h2 className={styles.sectionTitle}>Sessions</h2>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Student</th>
              <th scope="col">Date</th>
              <th scope="col">Status</th>
              <th scope="col">Score</th>
              <th scope="col" aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {sessions.map((session) => {
              const dt = parseSessionDate(session.dateIso)
              const dateLabel = dt
                ? dt.toLocaleString(undefined, {
                    month: 'short',
                    day: 'numeric',
                    hour: 'numeric',
                    minute: '2-digit',
                  })
                : '—'
              const scoreLabel =
                session.status === 'pending'
                  ? 'Pending'
                  : session.status === 'failed'
                    ? 'Failed'
                  : session.score != null
                    ? session.score.toFixed(1)
                    : '—'
              return (
                <tr key={session.id}>
                  <td>{session.studentName}</td>
                  <td>{dateLabel}</td>
                  <td className={styles.statusCell} data-status={session.status}>
                    {formatStatusLabel(session.status)}
                  </td>
                  <td>{scoreLabel}</td>
                  <td className={styles.actionsCell}>
                    <Link
                      className={styles.linkButton}
                      to={ROUTE_PATH.TEACHER_SESSION_DETAIL.replace(
                        ':sessionId',
                        encodeURIComponent(session.id),
                      )}
                    >
                      Open
                    </Link>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>
    </main>
  )
}
