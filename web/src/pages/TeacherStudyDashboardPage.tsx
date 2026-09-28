import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { getStudyDashboardSummary } from '../api/studyDashboard'
import { ROUTE_PATH } from '../routes/paths'
import type {
  StudyDashboardSessionRow,
  StudyDashboardSummary,
  StudyDashboardTopicRow,
  StudyDashboardTotals,
} from '../types/studyDashboard'
import styles from './TeacherStudyDashboardPage.module.css'

const formatPercent = (value: number | null | undefined) => (value == null ? '—' : `${value.toFixed(1)}%`)

const formatRating = (value: number | null | undefined) => (value == null ? '—' : value.toFixed(1))

const formatNumber = (value: number | null | undefined, digits = 1) => (value == null ? '—' : value.toFixed(digits))

const formatDuration = (valueMs: number | null | undefined) => {
  if (valueMs == null) return '—'
  if (valueMs < 1000) return `${Math.round(valueMs)} ms`
  const seconds = valueMs / 1000
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  return `${(seconds / 60).toFixed(1)}m`
}

const formatBool = (value: boolean) => (value ? 'Yes' : 'No')

const average = (values: Array<number | null | undefined>) => {
  const xs = values.filter((value): value is number => typeof value === 'number')
  if (xs.length === 0) return null
  return xs.reduce((sum, value) => sum + value, 0) / xs.length
}

type StudentSummary = {
  studentId: string
  sessions: StudyDashboardSessionRow[]
  sessionCount: number
  completedCount: number
  completionRate: number
  surveyCount: number
  surveySubmitRate: number
  totalQuestions: number
  totalCaptures: number
  totalAmaTurns: number
  questionsAnsweredOral: number
  questionsAnsweredPaper: number
  oralTranscriptCount: number
  avgTranscriptionDurationMs: number | null
  avgOralGradeDurationMs: number | null
  avgHelpfulness: number | null
  avgSessionDurationMs: number | null
  avgGradeDurationMs: number | null
  latestDayRunId: string
  topics: string[]
  errorCount: number
}

function buildStudentSummaries(sessions: StudyDashboardSessionRow[]): StudentSummary[] {
  const groups = new Map<string, StudyDashboardSessionRow[]>()
  for (const session of sessions) {
    const key = session.studentId || 'Unknown'
    groups.set(key, [...(groups.get(key) ?? []), session])
  }

  return Array.from(groups.entries())
    .map(([studentId, group]) => {
      const completedCount = group.filter((session) => session.sessionCompleted).length
      const surveyCount = group.filter((session) => session.surveySubmitted).length
      const topics = Array.from(
        new Set(group.map((session) => session.topicId || session.course || 'Unknown').filter(Boolean)),
      )
      return {
        studentId,
        sessions: group,
        sessionCount: group.length,
        completedCount,
        completionRate: (completedCount / group.length) * 100,
        surveyCount,
        surveySubmitRate: (surveyCount / group.length) * 100,
        totalQuestions: group.reduce((sum, session) => sum + session.questionCount, 0),
        totalCaptures: group.reduce((sum, session) => sum + session.captureCount, 0),
        totalAmaTurns: group.reduce((sum, session) => sum + session.amaUserCount, 0),
        questionsAnsweredOral: group.reduce((sum, session) => sum + session.questionsAnsweredOral, 0),
        questionsAnsweredPaper: group.reduce((sum, session) => sum + session.questionsAnsweredPaper, 0),
        oralTranscriptCount: group.reduce((sum, session) => sum + session.oralTranscriptCount, 0),
        avgTranscriptionDurationMs: average(group.map((session) => session.avgTranscriptionDurationMs)),
        avgOralGradeDurationMs: average(group.map((session) => session.avgOralGradeDurationMs)),
        avgHelpfulness: average(group.map((session) => session.surveyHelpfulness)),
        avgSessionDurationMs: average(group.map((session) => session.sessionDurationMs)),
        avgGradeDurationMs: average(group.map((session) => session.avgGradeDurationMs)),
        latestDayRunId: group.map((session) => session.dayRunId).sort().at(-1) ?? '',
        topics,
        errorCount: group.reduce((sum, session) => sum + session.backendErrorCount + session.clientErrorCount, 0),
      }
    })
    .sort((a, b) => a.studentId.localeCompare(b.studentId, undefined, { numeric: true }))
}

function buildTotals(sessions: StudyDashboardSessionRow[]): StudyDashboardTotals {
  const studySessionsStarted = sessions.reduce((sum, session) => sum + session.studySessionsStarted, 0) || sessions.length
  const activatedSessions = sessions.filter((session) => session.activated).length
  const completedSessions = sessions.filter((session) => session.sessionCompleted).length
  const reachedPostSessionSummaryCount = sessions.filter((session) => session.reachedPostSessionSummary).length
  const surveySubmissions = sessions.filter((session) => session.surveySubmitted).length
  const repeatedUsageYesCount = sessions.filter((session) => session.surveyWouldUseAgain === true).length
  const repeatedUsageResponseCount = sessions.filter((session) => session.surveyWouldUseAgain !== null).length
  return {
    sessions: sessions.length,
    studySessionsStarted,
    students: new Set(sessions.map((session) => session.studentId || 'Unknown')).size,
    activatedSessions,
    activationRate: studySessionsStarted ? (activatedSessions / studySessionsStarted) * 100 : 0,
    completedSessions,
    completionRate: sessions.length ? (completedSessions / sessions.length) * 100 : 0,
    reachedPostSessionSummaryCount,
    reachedPostSessionSummaryRate: sessions.length ? (reachedPostSessionSummaryCount / sessions.length) * 100 : 0,
    surveySubmissions,
    surveySubmitRate: sessions.length ? (surveySubmissions / sessions.length) * 100 : 0,
    repeatedUsageYesCount,
    repeatedUsageResponseCount,
    repeatedUsageRate: repeatedUsageResponseCount ? (repeatedUsageYesCount / repeatedUsageResponseCount) * 100 : null,
    avgHelpfulness: average(sessions.map((session) => session.surveyHelpfulness)),
    avgEaseOfUse: average(sessions.map((session) => session.surveyEaseOfUse)),
    avgQuestionDifficulty: average(sessions.map((session) => session.surveyQuestionDifficulty)),
    avgSessionDurationMs: average(sessions.map((session) => session.sessionDurationMs)),
    avgGradeDurationMs: average(sessions.map((session) => session.avgGradeDurationMs)),
    avgTimeToFirstCaptureMs: average(sessions.map((session) => session.timeToFirstCaptureMs)),
    avgTimeWorkingMs: average(sessions.map((session) => session.avgTimeWorkingMs)),
    avgQuestionsPerSession: average(sessions.map((session) => session.questionCount)),
    avgPercentCorrectQuestions: average(sessions.map((session) => session.percentCorrectQuestions)),
    jetsonBackendErrorRate: average(sessions.map((session) => session.jetsonBackendErrorRate)),
    totalQuestions: sessions.reduce((sum, session) => sum + session.questionCount, 0),
    totalCaptures: sessions.reduce((sum, session) => sum + session.captureCount, 0),
    totalAmaTurns: sessions.reduce((sum, session) => sum + session.amaUserCount, 0),
    backendErrorCount: sessions.reduce((sum, session) => sum + session.backendErrorCount, 0),
    clientErrorCount: sessions.reduce((sum, session) => sum + session.clientErrorCount, 0),
    questionsAnsweredOral: sessions.reduce((sum, session) => sum + session.questionsAnsweredOral, 0),
    questionsAnsweredPaper: sessions.reduce((sum, session) => sum + session.questionsAnsweredPaper, 0),
    oralUploadCount: sessions.reduce((sum, session) => sum + session.oralUploadCount, 0),
    oralTranscriptCount: sessions.reduce((sum, session) => sum + session.oralTranscriptCount, 0),
    oralRetakeCount: sessions.reduce((sum, session) => sum + session.oralRetakeCount, 0),
    oralRecordStartedCount: sessions.reduce((sum, session) => sum + session.oralRecordStartedCount, 0),
    avgOralRecordDurationMs: average(sessions.map((session) => session.avgOralRecordDurationMs)),
    avgTranscriptionDurationMs: average(sessions.map((session) => session.avgTranscriptionDurationMs)),
    p95TranscriptionDurationMs: null,
    avgUploadToTranscriptMs: average(sessions.map((session) => session.uploadToTranscriptMs)),
    avgPaperGradeDurationMs: average(sessions.map((session) => session.avgPaperGradeDurationMs)),
    avgOralGradeDurationMs: average(sessions.map((session) => session.avgOralGradeDurationMs)),
    p95OralGradeDurationMs: null,
    oralTranscriptTotalChars: sessions.reduce((sum, session) => sum + session.oralTranscriptTotalChars, 0),
  }
}

const countNumberValues = (values: Array<number | null | undefined>) =>
  values.filter((value): value is number => typeof value === 'number').length

function buildTopicSummaries(sessions: StudyDashboardSessionRow[]): StudyDashboardTopicRow[] {
  const groups = new Map<string, StudyDashboardSessionRow[]>()
  for (const session of sessions) {
    const course = session.course || 'Unknown'
    const topic = session.topicId || 'Unknown'
    const key = `${course}::${topic}`
    groups.set(key, [...(groups.get(key) ?? []), session])
  }

  return Array.from(groups.entries())
    .map(([key, group]) => {
      const [course, topicId] = key.split('::')
      const completed = group.filter((session) => session.sessionCompleted).length
      return {
        course,
        topicId,
        sessions: group.length,
        completionRate: group.length ? (completed / group.length) * 100 : 0,
        avgHelpfulness: average(group.map((session) => session.surveyHelpfulness)),
        avgPercentCorrectQuestions: average(group.map((session) => session.percentCorrectQuestions)),
        avgGradeDurationMs: average(group.map((session) => session.avgGradeDurationMs)),
        questionsAnsweredOral: group.reduce((sum, session) => sum + session.questionsAnsweredOral, 0),
        questionsAnsweredPaper: group.reduce((sum, session) => sum + session.questionsAnsweredPaper, 0),
        oralTranscriptCount: group.reduce((sum, session) => sum + session.oralTranscriptCount, 0),
        avgTranscriptionDurationMs: average(group.map((session) => session.avgTranscriptionDurationMs)),
        avgOralGradeDurationMs: average(group.map((session) => session.avgOralGradeDurationMs)),
      }
    })
    .sort((a, b) => a.course.localeCompare(b.course) || a.topicId.localeCompare(b.topicId))
}

type SurveyTextGroup = {
  title: string
  prompt: string
  answers: Array<{
    sessionId: string
    studentId: string
    dayRunId: string
    answer: string
  }>
}

function buildSurveyTextGroups(sessions: StudyDashboardSessionRow[]): SurveyTextGroup[] {
  const fields: Array<{
    title: string
    prompt: string
    read: (session: StudyDashboardSessionRow) => string
  }> = [
    {
      title: 'What students liked',
      prompt: 'What did you like about this session?',
      read: (session) => session.surveyLiked,
    },
    {
      title: 'Frustrations',
      prompt: 'What did you hate or find frustrating?',
      read: (session) => session.surveyDisliked,
    },
    {
      title: 'Suggested improvements',
      prompt: 'What would have made this session better for you today?',
      read: (session) => session.surveyImprovements,
    },
    {
      title: 'Anything else',
      prompt: 'Anything else we should know about your experience today?',
      read: (session) => session.surveyAnythingElse,
    },
    {
      title: 'Response quality feedback',
      prompt: 'How did you find the responses?',
      read: (session) => session.surveyResponseFeedback,
    },
  ]

  return fields.map((field) => ({
    title: field.title,
    prompt: field.prompt,
    answers: sessions
      .map((session) => ({
        sessionId: session.sessionId,
        studentId: session.studentId,
        dayRunId: session.dayRunId,
        answer: field.read(session).trim(),
      }))
      .filter((entry) => entry.answer.length > 0),
  }))
}

function KpiCard({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <article className={styles.kpiCard}>
      <p className={styles.kpiLabel}>{label}</p>
      <p className={styles.kpiValue}>{value}</p>
      <p className={styles.kpiHint}>{hint}</p>
    </article>
  )
}

export function TeacherStudyDashboardPage() {
  const [data, setData] = useState<StudyDashboardSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedStudentId, setSelectedStudentId] = useState<string | null>(null)
  const [filterStudentIds, setFilterStudentIds] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const next = await getStudyDashboardSummary()
        if (!cancelled) setData(next)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load dashboard.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  const allStudentSummaries = useMemo(() => buildStudentSummaries(data?.sessions ?? []), [data?.sessions])
  const visibleSessions = useMemo(() => {
    const sessions = data?.sessions ?? []
    if (filterStudentIds.length === 0) return sessions
    const allowed = new Set(filterStudentIds)
    return sessions.filter((session) => allowed.has(session.studentId || 'Unknown'))
  }, [data?.sessions, filterStudentIds])
  const studentSummaries = useMemo(() => buildStudentSummaries(visibleSessions), [visibleSessions])
  const topicSummaries = useMemo(() => buildTopicSummaries(visibleSessions), [visibleSessions])
  const surveyTextGroups = useMemo(() => buildSurveyTextGroups(visibleSessions), [visibleSessions])
  const selectedStudent = useMemo(() => {
    if (studentSummaries.length === 0) return null
    if (!selectedStudentId) return studentSummaries[0]
    return studentSummaries.find((student) => student.studentId === selectedStudentId) ?? studentSummaries[0]
  }, [selectedStudentId, studentSummaries])
  const totals = useMemo(() => buildTotals(visibleSessions), [visibleSessions])
  const timeWorkingSessionCount = useMemo(
    () => countNumberValues(visibleSessions.map((session) => session.avgTimeWorkingMs)),
    [visibleSessions],
  )
  const ratingSurveyCount = useMemo(
    () => countNumberValues(visibleSessions.map((session) => session.surveyHelpfulness)),
    [visibleSessions],
  )
  const filterLabel =
    filterStudentIds.length === 0
      ? 'Showing all students'
      : `Showing ${filterStudentIds.length} selected student${filterStudentIds.length === 1 ? '' : 's'}`

  const toggleFilterStudent = (studentId: string) => {
    setFilterStudentIds((current) =>
      current.includes(studentId) ? current.filter((id) => id !== studentId) : [...current, studentId],
    )
    setSelectedStudentId(studentId)
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <p className={styles.breadcrumb}>
          <Link to={ROUTE_PATH.TEACHER_HOME} className={styles.breadcrumbLink}>
            Teacher Console
          </Link>
          <span className={styles.breadcrumbSeparator}>/</span>
          <span>Study Dashboard</span>
        </p>
        <h1 className={styles.title}>Study Mode Dashboard</h1>
        <p className={styles.subtitle}>
          Analytics from Jetson-local Study Mode metrics, grouped by student, day run, session, and topic.
        </p>
      </header>

      {loading ? <p className={styles.notice}>Loading Study Mode metrics…</p> : null}
      {error ? <p className={styles.errorText}>Could not load dashboard: {error}</p> : null}

      {data ? (
        <>
          <section className={styles.kpiGrid} aria-label="Study Mode KPIs">
            <KpiCard
              label="Study Sessions Started"
              value={String(totals.studySessionsStarted)}
              hint={`${totals.students} students in current filter`}
            />
            <KpiCard
              label="Activation Rate"
              value={formatPercent(totals.activationRate)}
              hint={`${totals.activatedSessions} sessions with at least one answer submitted`}
            />
            <KpiCard
              label="Helpfulness Score"
              value={formatRating(totals.avgHelpfulness)}
              hint="Average 1 to 5 survey rating"
            />
            <KpiCard
              label="Ease of Usage"
              value={formatRating(totals.avgEaseOfUse)}
              hint="Average 1 to 5 survey rating"
            />
            <KpiCard
              label="Repeated Usage Survey"
              value={formatPercent(totals.repeatedUsageRate)}
              hint={`${totals.repeatedUsageYesCount} yes / ${totals.repeatedUsageResponseCount} responses`}
            />
            <KpiCard
              label="Difficulty Score"
              value={formatRating(totals.avgQuestionDifficulty)}
              hint="Average perceived difficulty"
            />
            <KpiCard
              label="Paper vs Oral Questions"
              value={`${totals.questionsAnsweredPaper} / ${totals.questionsAnsweredOral}`}
              hint="Questions answered on paper vs spoken (across filter)"
            />
            <KpiCard
              label="STT Latency"
              value={formatDuration(totals.avgTranscriptionDurationMs)}
              hint={`${totals.oralTranscriptCount} spoken submissions transcribed`}
            />
            <KpiCard
              label="Upload → Transcript"
              value={formatDuration(totals.avgUploadToTranscriptMs)}
              hint="End-to-end after I'm done speaking"
            />
            <KpiCard
              label="Oral Grade Latency"
              value={formatDuration(totals.avgOralGradeDurationMs)}
              hint="Average evaluate time for spoken answers"
            />
            <KpiCard
              label="Paper Grade Latency"
              value={formatDuration(totals.avgPaperGradeDurationMs)}
              hint="Average evaluate time for camera captures"
            />
            <KpiCard
              label="Latency (all grades)"
              value={formatDuration(totals.avgGradeDurationMs)}
              hint="Average grading feedback time"
            />
            <KpiCard
              label="Time Spent on Question"
              value={formatDuration(totals.avgTimeWorkingMs)}
              hint={`Average question shown to evaluate click (${timeWorkingSessionCount} sessions with data)`}
            />
            <KpiCard
              label="Ask Me Anything Uses"
              value={String(totals.totalAmaTurns)}
              hint="Total student tutor-chat turns"
            />
            <KpiCard
              label="Questions / Session"
              value={formatNumber(totals.avgQuestionsPerSession)}
              hint={`${totals.totalQuestions} total questions`}
            />
            <KpiCard
              label="Reached Post-Session Summary"
              value={formatPercent(totals.reachedPostSessionSummaryRate)}
              hint={`${totals.reachedPostSessionSummaryCount} sessions reached review`}
            />
            <KpiCard
              label="Right Answers Over Sessions"
              value={formatPercent(totals.avgPercentCorrectQuestions)}
              hint="Average percent correct questions"
            />
            <KpiCard
              label="Jetson Backend Error Rate"
              value={formatPercent(totals.jetsonBackendErrorRate)}
              hint={`${totals.backendErrorCount} backend errors logged`}
            />
          </section>

          <section className={styles.grid}>
            <article className={styles.card}>
              <h2>Session Funnel</h2>
              <div className={styles.funnel}>
                <div>
                  <span>Started</span>
                  <strong>{totals.studySessionsStarted}</strong>
                </div>
                <div>
                  <span>Activated</span>
                  <strong>{totals.activatedSessions}</strong>
                </div>
                <div>
                  <span>Completed</span>
                  <strong>{totals.completedSessions}</strong>
                </div>
                <div>
                  <span>Reached Review</span>
                  <strong>{visibleSessions.filter((row) => row.reachedPostSessionSummary).length}</strong>
                </div>
                <div>
                  <span>Survey Submitted</span>
                  <strong>{totals.surveySubmissions}</strong>
                </div>
              </div>
            </article>

            <article className={styles.card}>
              <h2>Spoken Answers</h2>
              <p className={styles.metricLine}>
                <strong>Oral questions:</strong> {totals.questionsAnsweredOral}
              </p>
              <p className={styles.metricLine}>
                <strong>Paper questions:</strong> {totals.questionsAnsweredPaper}
              </p>
              <p className={styles.metricLine}>
                <strong>Transcripts:</strong> {totals.oralTranscriptCount} ({totals.oralTranscriptTotalChars} chars)
              </p>
              <p className={styles.metricLine}>
                <strong>Recordings started:</strong> {totals.oralRecordStartedCount}
              </p>
              <p className={styles.metricLine}>
                <strong>Oral retakes:</strong> {totals.oralRetakeCount}
              </p>
              <p className={styles.metricLine}>
                <strong>Avg record duration:</strong> {formatDuration(totals.avgOralRecordDurationMs)}
              </p>
            </article>

            <article className={styles.card}>
              <h2>System Health</h2>
              <p className={styles.metricLine}>
                <strong>Backend errors:</strong> {totals.backendErrorCount}
              </p>
              <p className={styles.metricLine}>
                <strong>Client errors:</strong> {totals.clientErrorCount}
              </p>
              <p className={styles.metricLine}>
                <strong>Empty metric placeholders:</strong> {data.malformedFiles}
                {data.malformedFiles > 0 ? (
                  <span className={styles.helper}>
                    {' '}
                    (session folders with no events — not counted)
                  </span>
                ) : null}
              </p>
              <p className={styles.helper}>Source: {data.sourceRoot || 'Central API not configured'}</p>
            </article>
          </section>

          <section className={styles.card} aria-labelledby="student-filter-title">
            <div className={styles.filterHeader}>
              <div>
                <h2 id="student-filter-title">Filter by Student ID</h2>
                <p className={styles.helper}>{filterLabel}</p>
              </div>
              <div className={styles.filterActions}>
                <button
                  type="button"
                  className={styles.smallButton}
                  onClick={() => setFilterStudentIds(allStudentSummaries.map((student) => student.studentId))}
                >
                  Select all
                </button>
                <button type="button" className={styles.smallButton} onClick={() => setFilterStudentIds([])}>
                  Clear
                </button>
              </div>
            </div>
            {allStudentSummaries.length === 0 ? (
              <p className={styles.helper}>No student IDs found yet.</p>
            ) : (
              <div className={styles.filterList} aria-label="Student ID filters">
                {allStudentSummaries.map((student) => (
                  <label key={student.studentId} className={styles.filterOption}>
                    <input
                      type="checkbox"
                      checked={filterStudentIds.includes(student.studentId)}
                      onChange={() => toggleFilterStudent(student.studentId)}
                    />
                    <span className={styles.mono}>{student.studentId}</span>
                    <span className={styles.filterCount}>{student.sessionCount} sessions</span>
                  </label>
                ))}
              </div>
            )}
          </section>

          <section className={styles.card}>
            <h2>Survey Answers</h2>
            <p className={styles.helper}>
              Survey responses in the current filter, grouped by question type.
            </p>

            <div className={styles.surveyStatsGrid}>
              <article className={styles.surveyStatCard}>
                <h3>Rating Questions</h3>
                <p>
                  <strong>Helpfulness:</strong> {formatRating(totals.avgHelpfulness)}
                </p>
                <p>
                  <strong>Ease of usage:</strong> {formatRating(totals.avgEaseOfUse)}
                </p>
                <p>
                  <strong>Difficulty:</strong> {formatRating(totals.avgQuestionDifficulty)}
                </p>
                <p className={styles.helper}>{ratingSurveyCount} sessions with rating answers</p>
              </article>

              <article className={styles.surveyStatCard}>
                <h3>Yes / No Question</h3>
                <p>
                  <strong>Would use again:</strong> {formatPercent(totals.repeatedUsageRate)}
                </p>
                <p className={styles.helper}>
                  {totals.repeatedUsageYesCount} yes / {totals.repeatedUsageResponseCount} responses
                </p>
              </article>
            </div>

            <div className={styles.surveyTextGrid}>
              {surveyTextGroups.map((group) => (
                <article key={group.title} className={styles.surveyTextGroup}>
                  <h3>{group.title}</h3>
                  <p className={styles.helper}>{group.prompt}</p>
                  {group.answers.length === 0 ? (
                    <p className={styles.helper}>No written answers for this question in the current filter.</p>
                  ) : (
                    <div className={styles.answerList}>
                      {group.answers.map((entry) => (
                        <figure key={`${group.title}-${entry.sessionId}`} className={styles.answerCard}>
                          <blockquote>{entry.answer}</blockquote>
                          <figcaption>
                            Student <span className={styles.mono}>{entry.studentId}</span> · {entry.dayRunId}
                          </figcaption>
                        </figure>
                      ))}
                    </div>
                  )}
                </article>
              ))}
            </div>
          </section>

          <section className={styles.card}>
            <h2>Topic Rollup</h2>
            {topicSummaries.length === 0 ? (
              <p className={styles.helper}>No topic metrics found yet.</p>
            ) : (
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Course</th>
                      <th>Topic</th>
                      <th>Sessions</th>
                      <th>Completion</th>
                      <th>Helpfulness</th>
                      <th>Correctness</th>
                      <th>Feedback Latency</th>
                      <th>Oral Q</th>
                      <th>Paper Q</th>
                      <th>STT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topicSummaries.map((topic) => (
                      <tr key={`${topic.course}-${topic.topicId}`}>
                        <td>{topic.course}</td>
                        <td>{topic.topicId}</td>
                        <td>{topic.sessions}</td>
                        <td>{formatPercent(topic.completionRate)}</td>
                        <td>{formatRating(topic.avgHelpfulness)}</td>
                        <td>{formatPercent(topic.avgPercentCorrectQuestions)}</td>
                        <td>{formatDuration(topic.avgGradeDurationMs)}</td>
                        <td>{topic.questionsAnsweredOral}</td>
                        <td>{topic.questionsAnsweredPaper}</td>
                        <td>{formatDuration(topic.avgTranscriptionDurationMs)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className={styles.card}>
            <h2>Students</h2>
            <p className={styles.helper}>
              Each row summarizes all Study Mode sessions for one student. Select a student to inspect their session history.
            </p>
            {studentSummaries.length === 0 ? (
              <p className={styles.helper}>No Study Mode student summaries found yet.</p>
            ) : (
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Student</th>
                      <th>Sessions</th>
                      <th>Completed</th>
                      <th>Survey Rate</th>
                      <th>Questions</th>
                      <th>Captures</th>
                      <th>Oral Q</th>
                      <th>Paper Q</th>
                      <th>AMA</th>
                      <th>STT</th>
                      <th>Helpfulness</th>
                      <th>Avg Duration</th>
                      <th>Topics</th>
                      <th>Errors</th>
                    </tr>
                  </thead>
                  <tbody>
                    {studentSummaries.map((student) => (
                      <tr
                        key={student.studentId}
                        className={student.studentId === selectedStudent?.studentId ? styles.selectedRow : styles.clickableRow}
                        onClick={() => setSelectedStudentId(student.studentId)}
                      >
                        <td className={styles.mono}>{student.studentId}</td>
                        <td>{student.sessionCount}</td>
                        <td>
                          {student.completedCount} / {student.sessionCount} ({formatPercent(student.completionRate)})
                        </td>
                        <td>{formatPercent(student.surveySubmitRate)}</td>
                        <td>{student.totalQuestions}</td>
                        <td>{student.totalCaptures}</td>
                        <td>{student.questionsAnsweredOral}</td>
                        <td>{student.questionsAnsweredPaper}</td>
                        <td>{student.totalAmaTurns}</td>
                        <td>{formatDuration(student.avgTranscriptionDurationMs)}</td>
                        <td>{formatRating(student.avgHelpfulness)}</td>
                        <td>{formatDuration(student.avgSessionDurationMs)}</td>
                        <td>{student.topics.slice(0, 3).join(', ') || 'Unknown'}</td>
                        <td>{student.errorCount}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {selectedStudent ? (
            <section className={styles.card}>
              <h2>Sessions for Student {selectedStudent.studentId}</h2>
              <p className={styles.helper}>
                {selectedStudent.sessionCount} sessions, {selectedStudent.totalQuestions} questions,{' '}
                {selectedStudent.totalCaptures} captures, {selectedStudent.questionsAnsweredOral} oral /{' '}
                {selectedStudent.questionsAnsweredPaper} paper questions, {selectedStudent.totalAmaTurns} tutor
                questions.
              </p>
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Session</th>
                      <th>Day</th>
                      <th>Course</th>
                      <th>Topic</th>
                      <th>Questions</th>
                      <th>Captures</th>
                      <th>Oral</th>
                      <th>Paper</th>
                      <th>Transcripts</th>
                      <th>STT</th>
                      <th>Oral grade</th>
                      <th>AMA</th>
                      <th>Completed</th>
                      <th>Survey</th>
                      <th>Helpfulness</th>
                      <th>Ease</th>
                      <th>Difficulty</th>
                      <th>Use Again</th>
                      <th>Duration</th>
                      <th>Time on Question</th>
                      <th>Feedback Latency</th>
                      <th>Right Answers</th>
                      <th>Jetson Error Rate</th>
                      <th>Errors</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedStudent.sessions.map((session) => (
                      <tr key={session.sessionId}>
                        <td className={styles.mono}>{session.sessionId}</td>
                        <td>{session.dayRunId}</td>
                        <td>{session.course || 'Unknown'}</td>
                        <td>{session.topicId || 'Unknown'}</td>
                        <td>{session.questionCount}</td>
                        <td>{session.captureCount}</td>
                        <td>{session.questionsAnsweredOral}</td>
                        <td>{session.questionsAnsweredPaper}</td>
                        <td>{session.oralTranscriptCount}</td>
                        <td>{formatDuration(session.avgTranscriptionDurationMs)}</td>
                        <td>{formatDuration(session.avgOralGradeDurationMs)}</td>
                        <td>{session.amaUserCount}</td>
                        <td>{formatBool(session.sessionCompleted)}</td>
                        <td>{formatBool(session.surveySubmitted)}</td>
                        <td>{formatRating(session.surveyHelpfulness)}</td>
                        <td>{formatRating(session.surveyEaseOfUse)}</td>
                        <td>{formatRating(session.surveyQuestionDifficulty)}</td>
                        <td>{session.surveyWouldUseAgain == null ? '—' : formatBool(session.surveyWouldUseAgain)}</td>
                        <td>{formatDuration(session.sessionDurationMs)}</td>
                        <td>{formatDuration(session.avgTimeWorkingMs)}</td>
                        <td>{formatDuration(session.avgGradeDurationMs)}</td>
                        <td>{formatPercent(session.percentCorrectQuestions)}</td>
                        <td>{formatPercent(session.jetsonBackendErrorRate)}</td>
                        <td>{session.backendErrorCount + session.clientErrorCount}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}
        </>
      ) : null}
    </main>
  )
}
