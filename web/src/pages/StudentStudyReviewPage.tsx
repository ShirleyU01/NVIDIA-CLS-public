import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { studentStudyGuideApi } from '../api/studentStudyGuide'
import { getStudentStudyReview, type StudyReview } from '../api/studentStudyReview'
import { StudyMathMarkdown } from '../components/StudyMathMarkdown'
import { ROUTE_PATH } from '../routes/paths'
import type { StudyStudentFeedback } from '../types/studyFeedback'
import styles from './StudentStudyReviewPage.module.css'

/**
 * Post-session feedback page for study mode.
 *
 * On mount we begin polling ``GET /sessions/:id`` every few seconds. While
 * the Jetson is still generating feedback (or central hasn't seen the
 * artifact yet) we render a friendly loader; once ``study_feedback`` is
 * present we render three standardized narrative sections that summarize
 * the student's in-session per-capture feedback:
 *
 * - High-level takeaways
 * - Areas to improve
 * - Next Steps (concrete advice)
 */

const POLL_INTERVAL_MS = 3000

interface FeedbackSectionProps {
  title: string
  items: string[]
  emptyText: string
  testId: string
  extraClassName?: string
}

function FeedbackSection({
  title,
  items,
  emptyText,
  testId,
  extraClassName,
}: FeedbackSectionProps) {
  const className = extraClassName
    ? `${styles.section} ${extraClassName}`
    : styles.section
  return (
    <section className={className} aria-label={title} data-testid={testId}>
      <h3 className={styles.sectionTitle}>{title}</h3>
      {items.length > 0 ? (
        <ul className={styles.sectionList}>
          {items.map((item, idx) => (
            <li key={`${testId}-${idx}`} className={styles.sectionItem}>
              <StudyMathMarkdown text={item} className={styles.sectionItemMarkdown} />
            </li>
          ))}
        </ul>
      ) : (
        <p className={styles.sectionEmpty}>{emptyText}</p>
      )}
    </section>
  )
}

function FeedbackCard({ feedback }: { feedback: StudyStudentFeedback }) {
  return (
    <section
      className={styles.card}
      aria-label="Post-session study feedback"
      data-tour="student-study-review-results"
    >
      <h2 className={styles.questionTitle}>
        {feedback.question || 'Your study question'}
      </h2>
      <FeedbackSection
        title="High-level takeaways"
        items={feedback.high_level_takeaways}
        emptyText="No high-level takeaways were generated for this run."
        testId="study-section-takeaways"
      />
      <FeedbackSection
        title="Areas to improve"
        items={feedback.areas_to_improve}
        emptyText="No specific gaps were flagged this run."
        testId="study-section-areas"
      />
      <FeedbackSection
        title="Next steps"
        items={feedback.next_steps}
        emptyText="No next-step suggestions were generated for this run."
        testId="study-section-next"
        extraClassName={styles.sectionNext}
      />
    </section>
  )
}

export function StudentStudyReviewPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const [review, setReview] = useState<StudyReview>({ status: 'pending', feedback: null })
  const [error, setError] = useState<string | null>(null)
  const [finishing, setFinishing] = useState(false)
  const cancelledRef = useRef(false)
  const loggedReadyRef = useRef(false)

  useEffect(() => {
    if (!sessionId) return
    void studentStudyGuideApi.logClientEvent(sessionId, { type: 'review_page_viewed', data: {} })
  }, [sessionId])

  useEffect(() => {
    if (!sessionId) return
    const isReady = review.status === 'ready' && review.feedback !== null
    if (!isReady || loggedReadyRef.current) return
    loggedReadyRef.current = true
    void studentStudyGuideApi.logClientEvent(sessionId, { type: 'review_feedback_ready', data: {} })
  }, [sessionId, review])

  useEffect(() => {
    if (!sessionId) return
    cancelledRef.current = false
    let timer: number | undefined

    const poll = async () => {
      try {
        const next = await getStudentStudyReview(sessionId)
        if (cancelledRef.current) return
        setReview(next)
        setError(null)
        if (next.status !== 'ready') {
          timer = window.setTimeout(poll, POLL_INTERVAL_MS)
        }
      } catch (err) {
        if (cancelledRef.current) return
        setError(err instanceof Error ? err.message : 'Failed to load study feedback.')
        timer = window.setTimeout(poll, POLL_INTERVAL_MS)
      }
    }

    void poll()
    return () => {
      cancelledRef.current = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [sessionId])

  if (!sessionId) {
    return (
      <main className={styles.page}>
        <p className={styles.error} role="alert">
          Missing session id.
        </p>
      </main>
    )
  }

  const isReady = review.status === 'ready' && review.feedback !== null
  const feedback = review.feedback
  const postSessionPath = ROUTE_PATH.STUDENT_STUDY_POST_SESSION.replace(':sessionId', sessionId)

  const handleFinish = async () => {
    if (finishing) return
    void studentStudyGuideApi.logClientEvent(sessionId, { type: 'review_finish_clicked', data: {} })
    setFinishing(true)
    navigate(postSessionPath)
  }

  return (
    <main className={styles.page} aria-live="polite">
      <header className={styles.header}>
        <p className={styles.kicker}>Study session feedback</p>
        <h1 className={styles.title}>How did you do?</h1>
        <p className={styles.subtitle}>Session {sessionId}</p>
      </header>

      {!isReady || !feedback ? (
        <section
          className={styles.loaderPanel}
          data-testid="study-review-loader"
          data-tour="student-study-review-results"
        >
          <div className={styles.spinner} aria-hidden />
          <p className={styles.loaderText}>Preparing your feedback…</p>
          <p className={styles.loaderHint}>
            This usually takes 10-20 seconds while we review your captures.
          </p>
          {error ? (
            <p className={styles.error} role="alert">
              {error}
            </p>
          ) : null}
        </section>
      ) : (
        <FeedbackCard feedback={feedback} />
      )}

      <footer className={styles.footer}>
        <button
          type="button"
          className={styles.doneLink}
          data-tour="student-review-finish"
          onClick={handleFinish}
          disabled={finishing}
        >
          {finishing ? 'Finishing...' : 'Finish'}
        </button>
      </footer>
    </main>
  )
}
