import { useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'

import type { PracticeQuestionPayload } from '../api/questionBank'
import { questionBankApi } from '../api/questionBank'
import { studentStudyGuideApi } from '../api/studentStudyGuide'
import { StudyMathMarkdown } from '../components/StudyMathMarkdown'
import { ROUTE_PATH } from '../routes/paths'
import styles from './StudentStudyConfigPage.module.css'

const CENTRAL_API_BASE_URL = import.meta.env.VITE_CENTRAL_API_BASE_URL
const PRACTICE_ASSESSMENT_ID = (import.meta.env.VITE_PRACTICE_ASSESSMENT_ID as string | undefined)?.trim() ?? ''

const MIN_QUESTIONS = 1
const MAX_QUESTIONS = 20

function isValidStudentId(value: string): boolean {
  const trimmed = value.trim()
  if (!/^\d+$/.test(trimmed)) return false
  return Number(trimmed) > 0
}

/** Parse draft text; empty, non-numeric, or below min (e.g. 0) → null (caller treats as incomplete). */
function parseQuestionCountDraft(s: string): number | null {
  const t = s.trim()
  if (t === '') return null
  const n = Number.parseInt(t, 10)
  if (!Number.isFinite(n) || n < MIN_QUESTIONS) return null
  return Math.min(MAX_QUESTIONS, n)
}

export function StudentStudyConfigPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  const assessmentIdFromQuery = params.get('assessmentId') ?? ''
  const studentIdFromQuery = params.get('studentId')?.trim() ?? ''
  const storedStudentId = (() => {
    try {
      return window.sessionStorage.getItem('study:studentId')?.trim() ?? ''
    } catch {
      return ''
    }
  })()
  const studentId = isValidStudentId(studentIdFromQuery)
    ? studentIdFromQuery
    : isValidStudentId(storedStudentId)
      ? storedStudentId
      : ''
  const assessmentId = assessmentIdFromQuery || PRACTICE_ASSESSMENT_ID || 'demo-bayes-oral-exam'
  const dayRunId = (() => {
    try {
      return window.sessionStorage.getItem('study:dayRunId') ?? ''
    } catch {
      return ''
    }
  })()

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [courses, setCourses] = useState<{ id: string; title: string }[]>([])
  const [courseId, setCourseId] = useState('')
  const [topics, setTopics] = useState<{ id: string; name: string }[]>([])
  const [topicId, setTopicId] = useState('')
  /** String while typing so the field can be cleared/edited; clamp on blur / submit. */
  const [questionCountDraft, setQuestionCountDraft] = useState('3')
  const [seenQuestions, setSeenQuestions] = useState<PracticeQuestionPayload[]>([])
  const [selectedReviewQuestionIds, setSelectedReviewQuestionIds] = useState<string[]>([])
  const [seenLoading, setSeenLoading] = useState(false)
  const [seenError, setSeenError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      if (!CENTRAL_API_BASE_URL) return
      try {
        const list = await questionBankApi.listCourses()
        if (!cancelled) setCourses(list)
      } catch {
        if (!cancelled) setCourses([])
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      if (!courseId) {
        setTopics([])
        setTopicId('')
        return
      }
      try {
        const list = await questionBankApi.listTopics(courseId)
        if (!cancelled) {
          setTopics(list)
          setTopicId((prev) => (list.some((t) => t.id === prev) ? prev : (list[0]?.id ?? '')))
        }
      } catch {
        if (!cancelled) {
          setTopics([])
          setTopicId('')
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [courseId])

  useEffect(() => {
    let cancelled = false
    const loadSeenQuestions = async () => {
      if (!CENTRAL_API_BASE_URL || !studentId || !courseId || !topicId) {
        setSeenQuestions([])
        setSelectedReviewQuestionIds([])
        setSeenLoading(false)
        setSeenError(null)
        return
      }
      setSeenLoading(true)
      setSeenError(null)
      setSelectedReviewQuestionIds([])
      try {
        const list = await questionBankApi.listSeenQuestions(courseId, studentId, topicId)
        if (!cancelled) setSeenQuestions(list)
      } catch {
        if (!cancelled) {
          setSeenQuestions([])
          setSeenError('Could not load previous questions for review.')
        }
      } finally {
        if (!cancelled) setSeenLoading(false)
      }
    }
    void loadSeenQuestions()
    return () => {
      cancelled = true
    }
  }, [courseId, studentId, topicId])

  const parsedQuestionCount = parseQuestionCountDraft(questionCountDraft)
  const wantsQuestionBank =
    Boolean(CENTRAL_API_BASE_URL) &&
    courses.length > 0 &&
    Boolean(courseId) &&
    Boolean(topicId)

  useEffect(() => {
    if (studentId) return
    const next = new URLSearchParams()
    if (assessmentIdFromQuery) next.set('assessmentId', assessmentIdFromQuery)
    navigate(`${ROUTE_PATH.STUDENT_STUDY_ID}${next.toString() ? `?${next.toString()}` : ''}`, {
      replace: true,
    })
  }, [assessmentIdFromQuery, navigate, studentId])

  const startQuestionBankRun = async (
    practiceQuestions: PracticeQuestionPayload[],
    requestedCount: number,
  ) => {
    if (!assessmentIdFromQuery && !PRACTICE_ASSESSMENT_ID) {
      setError(
        'Question-bank practice needs an assessment id: open Study from an exam row, or set VITE_PRACTICE_ASSESSMENT_ID for a dedicated practice assessment.',
      )
      return
    }
    const numericAid = Number(assessmentIdFromQuery || PRACTICE_ASSESSMENT_ID)
    if (Number.isNaN(numericAid)) {
      setError('Invalid assessment id for central session. Use a numeric assessment id or set VITE_PRACTICE_ASSESSMENT_ID.')
      return
    }
    const { sessionId } = await studentStudyGuideApi.createRun({
      assessmentId: String(numericAid),
      studentId,
      dayRunId: dayRunId || undefined,
      practiceQuestions,
      studyPlan: {
        course: courseId,
        topic_id: topicId,
        requested_count: requestedCount,
        question_ids: practiceQuestions.map((q) => q.id),
      },
    })
    try {
      window.sessionStorage.setItem(`study:assessmentId:${sessionId}`, String(numericAid))
      window.sessionStorage.setItem(`study:studentId:${sessionId}`, studentId)
    } catch {
      // ignore
    }
    navigate(
      `${ROUTE_PATH.STUDENT_STUDY_SESSION}?sessionId=${encodeURIComponent(sessionId)}&assessmentId=${encodeURIComponent(String(numericAid))}`,
    )
  }

  const handleStartPractice = async () => {
    if (!studentId) {
      setError('Sign in with your student ID before starting practice.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      if (wantsQuestionBank) {
        const effectiveCount = parseQuestionCountDraft(questionCountDraft)
        if (effectiveCount == null) {
          setError(`Enter a number of questions between ${MIN_QUESTIONS} and ${MAX_QUESTIONS}.`)
          return
        }
        const practiceQuestions = await questionBankApi.selectQuestions(
          courseId,
          topicId,
          effectiveCount,
          studentId,
        )
        if (practiceQuestions.length === 0) {
          setError('You have already seen all questions for this topic. Review previous questions or choose another topic.')
          return
        }
        await startQuestionBankRun(practiceQuestions, effectiveCount)
        return
      }

      const { sessionId } = await studentStudyGuideApi.createRun({
        assessmentId,
        studentId,
        dayRunId: dayRunId || undefined,
      })
      try {
        window.sessionStorage.setItem(`study:assessmentId:${sessionId}`, assessmentId)
        window.sessionStorage.setItem(`study:studentId:${sessionId}`, studentId)
      } catch {
        // ignore
      }
      navigate(
        `${ROUTE_PATH.STUDENT_STUDY_SESSION}?sessionId=${encodeURIComponent(sessionId)}&assessmentId=${encodeURIComponent(assessmentId)}`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start study mode.')
    } finally {
      setBusy(false)
    }
  }

  const handleReviewToggle = (questionId: string) => {
    setSelectedReviewQuestionIds((prev) =>
      prev.includes(questionId) ? prev.filter((id) => id !== questionId) : [...prev, questionId],
    )
  }

  const handleStartReviewPractice = async () => {
    if (!studentId) {
      setError('Sign in with your student ID before starting practice.')
      return
    }
    const selected = seenQuestions.filter((q) => selectedReviewQuestionIds.includes(q.id))
    if (selected.length === 0) {
      setError('Choose at least one previous question to review.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await startQuestionBankRun(selected, selected.length)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start review practice.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className={styles.page}>
      <p className={styles.headline} data-tour="student-study-config-intro">
        Study Guide
      </p>
      <p className={styles.subHeadline}>Choose a topic and number of practice questions.</p>

      {CENTRAL_API_BASE_URL && courses.length > 0 ? (
        <section
          className={styles.bankForm}
          aria-label="Question bank practice"
          data-tour="student-study-config-bank"
        >
          <div className={styles.fieldRow}>
            <label className={styles.label} htmlFor="study-course">
              Course
            </label>
            <select
              id="study-course"
              className={styles.select}
              data-tour="student-study-course"
              value={courseId}
              onChange={(e) => setCourseId(e.target.value)}
            >
              <option value="">- Use assessment question only -</option>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>
          </div>
          {courseId ? (
            <>
              <div className={styles.fieldRow}>
                <label className={styles.label} htmlFor="study-topic">
                  Topic
                </label>
                <select
                  id="study-topic"
                  className={styles.select}
                  value={topicId}
                  onChange={(e) => setTopicId(e.target.value)}
                  disabled={!topics.length}
                >
                  {topics.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className={styles.fieldRow}>
                <label className={styles.label} htmlFor="study-count">
                  Number of questions
                </label>
                <input
                  id="study-count"
                  className={styles.numberInput}
                  type="text"
                  inputMode="numeric"
                  autoComplete="off"
                  aria-valuemin={MIN_QUESTIONS}
                  aria-valuemax={MAX_QUESTIONS}
                  aria-valuenow={parsedQuestionCount ?? undefined}
                  placeholder={`${MIN_QUESTIONS}–${MAX_QUESTIONS}`}
                  value={questionCountDraft}
                  onChange={(e) => {
                    let digits = e.target.value.replace(/\D/g, '').slice(0, 2)
                    if (digits !== '' && Number.parseInt(digits, 10) === 0) {
                      digits = ''
                    }
                    setQuestionCountDraft(digits)
                  }}
                  onBlur={() => {
                    const n = parseQuestionCountDraft(questionCountDraft)
                    setQuestionCountDraft(String(n ?? MIN_QUESTIONS))
                  }}
                />
              </div>
              <section className={styles.reviewPanel} aria-label="Review previous questions">
                <div>
                  <p className={styles.reviewTitle}>Review previous questions</p>
                  <p className={styles.reviewHint}>
                    Pick older questions from this topic if you want to practice them again.
                  </p>
                </div>
                {seenLoading ? <p className={styles.reviewNote}>Loading previous questions...</p> : null}
                {seenError ? <p className={styles.reviewError}>{seenError}</p> : null}
                {!seenLoading && !seenError && seenQuestions.length === 0 ? (
                  <p className={styles.reviewNote}>No previous questions for this topic yet.</p>
                ) : null}
                {seenQuestions.length > 0 ? (
                  <div className={styles.reviewList}>
                    {seenQuestions.map((q) => (
                      <label key={q.id} className={styles.reviewItem}>
                        <input
                          type="checkbox"
                          checked={selectedReviewQuestionIds.includes(q.id)}
                          onChange={() => handleReviewToggle(q.id)}
                        />
                        <span>
                          <StudyMathMarkdown text={q.text} className={styles.reviewQuestionText} />
                          <span className={styles.reviewQuestionId}>{q.id}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                ) : null}
                <button
                  type="button"
                  className={styles.reviewButton}
                  disabled={busy || selectedReviewQuestionIds.length === 0}
                  onClick={() => void handleStartReviewPractice()}
                >
                  Practice selected review questions
                </button>
              </section>
            </>
          ) : null}
        </section>
      ) : null}

      <button
        className={styles.beginButton}
        type="button"
        data-tour="student-start-practice"
        onClick={handleStartPractice}
        disabled={busy}
      >
        {busy ? 'Starting...' : 'Start Practice'}
      </button>

      {error ? (
        <p className={styles.error} role="alert">
          {error}
        </p>
      ) : null}
    </main>
  )
}
