import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { studentExamApi } from '../api/studentExam'
import { ROUTE_PATH } from '../routes/paths'
import type { ExamState } from '../types/exam'
import styles from './StudentSessionPage.module.css'

export function StudentSessionPage() {
  const [examState, setExamState] = useState<ExamState | null>(null)
  const [doneBusy, setDoneBusy] = useState(false)
  const [doneJustSent, setDoneJustSent] = useState(false)
  const [endBusy, setEndBusy] = useState(false)
  const [doneError, setDoneError] = useState<string | null>(null)
  const [endError, setEndError] = useState<string | null>(null)
  const location = useLocation()
  const navigate = useNavigate()

  const sessionId = useMemo(() => {
    const params = new URLSearchParams(location.search)
    return params.get('sessionId')
  }, [location.search])

  useEffect(() => {
    if (!sessionId) {
      return
    }

    let cancelled = false

    const fetchState = async () => {
      const state = await studentExamApi.getExamState(sessionId)
      if (!cancelled) {
        setExamState(state)
      }
    }

    void fetchState()
    const intervalId = window.setInterval(fetchState, 4000)

    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [sessionId])

  const renderExamStatusLabel = () => {
    if (!examState) return 'Connecting'
    if (doneBusy || doneJustSent) return 'Creating your next question…'
    if (examState.status === 'speaking') return 'Speaking'
    if (examState.status === 'thinking') return 'Creating your next question…'
    if (examState.status === 'done') return 'Complete'
    return 'Listening'
  }

  const isThinking = examState?.status === 'thinking'

  useEffect(() => {
    if (examState?.status === 'thinking' || examState?.status === 'speaking') {
      setDoneJustSent(false)
    }
  }, [examState?.status])

  const handleDoneSpeaking = async () => {
    if (!sessionId) return
    setDoneBusy(true)
    setDoneError(null)
    try {
      await studentExamApi.doneSpeaking(sessionId)
      setDoneJustSent(true)
    } catch (err) {
      setDoneError(err instanceof Error ? err.message : 'Failed to send done signal.')
    } finally {
      setDoneBusy(false)
    }
  }

  const handleEndExam = async () => {
    if (!sessionId) {
      navigate(ROUTE_PATH.STUDENT_DONE)
      return
    }

    setEndBusy(true)
    setEndError(null)
    try {
      await studentExamApi.endExam(sessionId)
      navigate(ROUTE_PATH.STUDENT_DONE)
    } catch (err) {
      setEndError(err instanceof Error ? err.message : 'Failed to end exam.')
    } finally {
      setEndBusy(false)
    }
  }

  return (
    <main className={styles.page}>
      {sessionId ? (
        <p className={styles.recordingBanner} aria-live="polite" data-tour="student-recording-status">
          <span className={styles.recordingDot} aria-hidden />
          Recording
        </p>
      ) : null}
      <section className={styles.left}>
        <section
          className={`${styles.panel} ${styles.question}`}
          aria-label="Current Question"
          data-tour="student-exam-question"
        >
          <header className={styles.questionHeader}>
            <p className={styles.questionKicker}>
              {examState || sessionId
                ? `Session ${examState?.sessionId ?? sessionId}`
                : 'Connecting to Exam'}
            </p>
            <p className={styles.statusPill}>{renderExamStatusLabel()}</p>
            {(doneBusy || doneJustSent || isThinking) ? (
              <div className={styles.thinkingProgress} role="progressbar" aria-valuetext="Creating your next question">
                <div className={styles.thinkingProgressBar} />
              </div>
            ) : null}
          </header>
          <p className={styles.questionBody}>
            {examState
              ? examState.questionText
              : 'Waiting for the proctor service to provide the first question...'}
          </p>
        </section>
        <section
          className={`${styles.panel} ${styles.transcript}`}
          aria-label="Running Transcript of the Conversation"
          data-tour="student-transcript"
        >
          <p className={styles.transcriptHint}>
            {examState
              ? examState.transcriptPreview
              : 'As you speak, a running transcript and key moments will appear here.'}
          </p>
        </section>
        <footer className={styles.footer}>
          <div className={styles.controls}>
            <button
              type="button"
              className={`${styles.doneSpeakingButton} ${doneJustSent ? styles.doneSpeakingButtonSent : ''}`}
              data-tour="student-done-speaking"
              onClick={handleDoneSpeaking}
              disabled={!sessionId || doneBusy}
            >
              {doneBusy ? 'Sending…' : doneJustSent ? 'Sent' : "I'm Done"}
            </button>
            {doneError ? (
              <p className={styles.doneError} role="alert">
                {doneError}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            className={styles.doneLink}
            data-tour="student-end-exam"
            onClick={handleEndExam}
            disabled={endBusy}
          >
            {endBusy ? 'Ending Exam…' : 'End Exam'}
          </button>
          {endError ? (
            <p className={styles.doneError} role="alert">
              {endError}
            </p>
          ) : null}
        </footer>
      </section>
    </main>
  )
}
