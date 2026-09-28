import { Link, useParams } from 'react-router-dom'
import { useEffect, useState } from 'react'

import { teacherApi } from '../api/teacher'
import { TeacherStudyFeedback } from '../components/TeacherStudyFeedback'
import { ROUTE_PATH } from '../routes/paths'
import styles from './TeacherSessionDetailPage.module.css'

const formatStatusLabel = (value: string) =>
  value
    .split(/[_-\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')

/** Minimum seconds between screenshots shown in evidence overview to avoid near-duplicates. */
const EVIDENCE_OVERVIEW_SCREENSHOT_INTERVAL_S = 2

function screenshotsSpacedByAtLeast(
  shots: Array<{ t: number; path: string; trigger_word: string; question_number: number }>,
  minIntervalSeconds: number
): typeof shots {
  if (shots.length === 0) return []
  const sorted = [...shots].sort((a, b) => a.t - b.t)
  const out: typeof shots = [sorted[0]]
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i].t - out[out.length - 1].t >= minIntervalSeconds) {
      out.push(sorted[i])
    }
  }
  return out
}

type EvidenceCriterion = {
  criterion_id?: string
  score?: number
  score_rationale_anchor?: string
  llm_confidence?: number
  evidence?: Array<{
    type?: string
    quote?: string
    t0?: number | null
    t1?: number | null
    why_it_supports?: string
  }>
  missing_evidence?: string[]
  suggested_followup_question?: string
  flags?: string[]
}

type EvidencePacketJson = {
  total_score?: number
  max_score?: number
  overall_confidence?: number
  criteria?: EvidenceCriterion[]
  flags?: string[]
}

export function TeacherSessionDetailPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const [detail, setDetail] = useState<import('../types/assessment').SessionDetail | null>(null)

  useEffect(() => {
    if (!sessionId) return
    let cancelled = false
    const load = async () => {
      try {
        const data = await teacherApi.getSession(sessionId)
        if (!cancelled) setDetail(data)
      } catch {
        // ignore for now; page will just show placeholders
      }
    }
    void load()
    const intervalId = window.setInterval(load, 4000)
    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [sessionId])

  const session = detail?.session
  const packet = detail?.evidence_packet
  const packetJson = (packet?.packetJson as EvidencePacketJson | undefined) ?? {}
  const criteria = packetJson.criteria ?? []
  const questionReviews = detail?.question_reviews ?? []
  const sessionScreenshots = detail?.session_screenshots ?? []
  const overviewScreenshots = screenshotsSpacedByAtLeast(
    sessionScreenshots,
    EVIDENCE_OVERVIEW_SCREENSHOT_INTERVAL_S
  )
  const centralApiBase = (import.meta.env.VITE_CENTRAL_API_BASE_URL as string)?.trim() ?? ''
  const evidenceJob = (detail?.artifacts?.evidence_job as Record<string, unknown> | undefined) ?? null
  const evidenceStatus = (evidenceJob?.status as string | undefined) ?? session?.status ?? 'unknown'
  const evidenceError = (evidenceJob?.error as string | undefined) ?? null
  const totalScore = packetJson.total_score
  const maxScore = packetJson.max_score
  const suggestedGrade =
    totalScore != null && maxScore && maxScore > 0 ? `${((totalScore / maxScore) * 100).toFixed(0)}%` : '—'

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <p className={styles.breadcrumb}>
          <Link to={ROUTE_PATH.TEACHER_ASSESSMENTS} className={styles.breadcrumbLink}>
            Past Exams
          </Link>
          <span className={styles.breadcrumbSeparator}>/</span>
          <span>{session?.assessmentId ?? ''}</span>
          <span className={styles.breadcrumbSeparator}>/</span>
          <span>{session?.studentName ?? ''}</span>
        </p>
        <h1 className={styles.title}>Session for {session?.studentName ?? sessionId}</h1>
        <p className={styles.subtitle}>Evidence Packet and Session Review</p>
      </header>

      <section className={styles.grid}>
        <section className={styles.card} aria-labelledby="evidence-overview-title">
          <h2 id="evidence-overview-title">Evidence Overview</h2>
          <p>
            <strong>Evidence Status:</strong> {formatStatusLabel(evidenceStatus)}
          </p>
          {evidenceError ? (
            <p className={styles.errorText}>
              <strong>Last Error:</strong> {evidenceError}
            </p>
          ) : null}
          <p className={styles.metaLine}>
            <strong>Score:</strong> {totalScore ?? '—'} / {maxScore ?? '—'}
          </p>
          {packetJson.flags?.length ? (
            <p className={styles.metaLine}>
              <strong>Packet Flags:</strong> {packetJson.flags.join(', ')}
            </p>
          ) : null}
          {overviewScreenshots.length > 0 ? (
            <>
              <p className={styles.evidenceHeading}>Screenshots</p>
              <p className={styles.helper}>
                Trigger-word captures (shown when more than {EVIDENCE_OVERVIEW_SCREENSHOT_INTERVAL_S}s apart).
              </p>
              <div className={styles.overviewScreenshotGrid}>
                {overviewScreenshots.map((shot, idx) => (
                  <figure key={`${shot.path}-${idx}`} className={styles.screenshotFigure}>
                    {centralApiBase && sessionId ? (
                      <img
                        src={`${centralApiBase}/sessions/${encodeURIComponent(sessionId)}/artifacts/files/${encodeURIComponent(shot.path)}`}
                        alt={`Screenshot at ${shot.t}s (trigger: ${shot.trigger_word})`}
                        className={styles.screenshotImg}
                      />
                    ) : (
                      <span className={styles.screenshotPlaceholder}>No preview</span>
                    )}
                    <figcaption className={styles.screenshotCaption}>
                      Q{shot.question_number} · {shot.t.toFixed(1)}s · "{shot.trigger_word}"
                    </figcaption>
                  </figure>
                ))}
              </div>
            </>
          ) : null}
        </section>

        <aside className={styles.card} aria-labelledby="suggested-grade-title">
          <h2 id="suggested-grade-title">Suggested Grade</h2>
          <p className={styles.gradeValue}>{suggestedGrade}</p>
          <p className={styles.gradeHint}>
            This comes from the evidence packet generated by the grading pipeline.
          </p>
        </aside>
      </section>

      <TeacherStudyFeedback
        studentFeedback={detail?.study_feedback ?? null}
        teacherSummary={detail?.study_teacher_summary ?? null}
      />

      <section className={styles.reviewSection} aria-label="Question-Level Review">
        <h2 className={styles.sectionTitle}>Question-Level Responses</h2>
        {questionReviews.length === 0 ? (
          <p className={styles.helper}>No question transcript data found for this session yet.</p>
        ) : (
          <div className={styles.questionList}>
            {questionReviews.map((q) => (
              <article key={q.index} className={styles.questionCard}>
                <p className={styles.questionTitle}>
                  Q{q.index}: {q.question || '(empty question)'}
                </p>
                <p className={styles.answerText}>
                  <strong>Student Answer:</strong> {q.answer || '(no answer captured)'}
                </p>
                {q.rubric_items.length ? (
                  <p className={styles.rubricItems}>
                    <strong>Rubric Items:</strong> {q.rubric_items.join(', ')}
                  </p>
                ) : null}
              </article>
            ))}
          </div>
        )}
      </section>

      {sessionScreenshots.length > 0 ? (
        <section className={styles.reviewSection} aria-label="Session Screenshots">
          <h2 className={styles.sectionTitle}>Screenshots (Deictic Captures)</h2>
          <p className={styles.helper}>
            Trigger-word screenshots from the exam. Shown in order by question and time.
          </p>
          <div className={styles.screenshotGrid}>
            {sessionScreenshots.map((shot, idx) => (
              <figure key={`${shot.path}-${idx}`} className={styles.screenshotFigure}>
                {centralApiBase && sessionId ? (
                  <img
                    src={`${centralApiBase}/sessions/${encodeURIComponent(sessionId)}/artifacts/files/${encodeURIComponent(shot.path)}`}
                    alt={`Screenshot at ${shot.t}s (trigger: ${shot.trigger_word})`}
                    className={styles.screenshotImg}
                  />
                ) : (
                  <span className={styles.screenshotPlaceholder}>No preview</span>
                )}
                <figcaption className={styles.screenshotCaption}>
                  Q{shot.question_number} · {shot.t.toFixed(1)}s · “{shot.trigger_word}”
                </figcaption>
              </figure>
            ))}
          </div>
        </section>
      ) : null}

      <section
        className={styles.reviewSection}
        aria-label="Criterion-Level Grading and Reasoning"
      >
        <h2 className={styles.sectionTitle}>Criterion Scoring and Reasoning</h2>
        {criteria.length === 0 ? (
          <p className={styles.helper}>No criterion-level evidence available in packet yet.</p>
        ) : (
          <div className={styles.criteriaList}>
            {criteria.map((criterion, idx) => (
              <article key={criterion.criterion_id ?? `criterion-${idx}`} className={styles.criterionCard}>
                <header className={styles.criterionHeader}>
                  <p className={styles.criterionTitle}>
                    {criterion.criterion_id ?? `Criterion ${idx + 1}`}
                  </p>
                  <p className={styles.criterionScore}>Score: {criterion.score ?? '—'}</p>
                </header>
                <p className={styles.metaLine}>
                  <strong>Rationale Anchor:</strong> {criterion.score_rationale_anchor ?? '—'}
                </p>
                {criterion.suggested_followup_question ? (
                  <p className={styles.metaLine}>
                    <strong>Suggested Follow-Up:</strong> {criterion.suggested_followup_question}
                  </p>
                ) : null}

                <div className={styles.evidenceList}>
                  <p className={styles.evidenceHeading}>Evidence and Reasoning</p>
                  {(criterion.evidence ?? []).length === 0 ? (
                    <p className={styles.helper}>No evidence snippets.</p>
                  ) : (
                    (criterion.evidence ?? []).map((ev, evIndex) => (
                      <div className={styles.evidenceItem} key={`${idx}-${evIndex}`}>
                        <p className={styles.metaLine}>
                          <strong>Type:</strong> {ev.type ?? '—'}
                        </p>
                        <p className={styles.metaLine}>
                          <strong>Quote:</strong> {ev.quote || '(empty quote)'}
                        </p>
                        <p className={styles.metaLine}>
                          <strong>Why It Supports:</strong> {ev.why_it_supports ?? '—'}
                        </p>
                      </div>
                    ))
                  )}
                </div>

                {criterion.flags?.length ? (
                  <p className={styles.metaLine}>
                    <strong>Flags:</strong> {criterion.flags.join(', ')}
                  </p>
                ) : null}
              </article>
            ))}
          </div>
        )}
      </section>

      <section className={styles.reviewSection} aria-label="Teacher Review Controls">
        <h2 className={styles.sectionTitle}>Your Decision</h2>
        <p className={styles.helper}>
          In a full implementation, this is where you would adjust scores per criterion and leave
          comments tied to the evidence.
        </p>
        <Link className={styles.primaryButton} to={ROUTE_PATH.TEACHER_DONE}>
          Mark Review Complete
        </Link>
      </section>
    </main>
  )
}
