import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { studentStudyGuideApi } from '../api/studentStudyGuide'
import { ROUTE_PATH } from '../routes/paths'
import styles from './StudentExitSurveyPage.module.css'

/**
 * Optional end-of-day exit survey.
 *
 * All questions must be answered before submit:
 * - Every rating / yes-no prompt is required.
 *
 * Network failures are still swallowed so a transient hiccup never traps the
 * student on this page after they have completed the form.
 */

const RATING_VALUES = [1, 2, 3, 4, 5] as const
const TEXT_MAX_LENGTH = 5000

interface RatingFieldProps {
  id: string
  label: string
  name: string
  value: number | null
  onChange: (v: number) => void
  leftLabel: string
  rightLabel: string
}

function RatingField({ id, label, name, value, onChange, leftLabel, rightLabel }: RatingFieldProps) {
  return (
    <div className={styles.question}>
      <p className={styles.questionLabel}>{label}</p>
      <p className={styles.questionPrompt} id={`${id}-prompt`}>
        {leftLabel} → {rightLabel}
      </p>
      <div
        className={styles.ratingRow}
        role="radiogroup"
        aria-labelledby={`${id}-prompt`}
        data-testid={`rating-${name}`}
      >
        {RATING_VALUES.map((v) => {
          const checked = value === v
          const optionClass = checked
            ? `${styles.ratingOption} ${styles.ratingOptionSelected}`
            : styles.ratingOption
          return (
            <label key={v} className={optionClass}>
              <input
                type="radio"
                name={name}
                value={v}
                checked={checked}
                onChange={() => onChange(v)}
                aria-label={`${label}: ${v}`}
              />
              {v}
            </label>
          )
        })}
      </div>
    </div>
  )
}

interface TextFieldProps {
  id: string
  label: string
  prompt: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
}

interface YesNoFieldProps {
  id: string
  label: string
  name: string
  value: boolean | null
  onChange: (v: boolean) => void
  prompt: string
}

function YesNoField({ id, label, name, value, onChange, prompt }: YesNoFieldProps) {
  const options = [
    { label: 'Yes', value: true },
    { label: 'No', value: false },
  ] as const

  return (
    <div className={styles.question}>
      <p className={styles.questionLabel}>{label}</p>
      <p className={styles.questionPrompt} id={`${id}-prompt`}>
        {prompt}
      </p>
      <div
        className={styles.ratingRow}
        role="radiogroup"
        aria-labelledby={`${id}-prompt`}
        data-testid={`rating-${name}`}
      >
        {options.map((option) => {
          const checked = value === option.value
          const optionClass = checked
            ? `${styles.ratingOption} ${styles.ratingOptionSelected}`
            : styles.ratingOption
          return (
            <label key={option.label} className={optionClass}>
              <input
                type="radio"
                name={name}
                value={String(option.value)}
                checked={checked}
                onChange={() => onChange(option.value)}
                aria-label={`${label}: ${option.label}`}
              />
              {option.label}
            </label>
          )
        })}
      </div>
    </div>
  )
}

function TextField({ id, label, prompt, value, onChange, placeholder }: TextFieldProps) {
  return (
    <div className={styles.question}>
      <p className={styles.questionLabel}>{label}</p>
      <label htmlFor={id} className={styles.questionPrompt}>
        {prompt}
      </label>
      <textarea
        id={id}
        className={styles.textArea}
        value={value}
        onChange={(e) => onChange(e.target.value.slice(0, TEXT_MAX_LENGTH))}
        placeholder={placeholder}
        aria-label={prompt}
      />
      <p className={styles.charCount} aria-live="polite">
        {value.length} / {TEXT_MAX_LENGTH}
      </p>
    </div>
  )
}

export function StudentExitSurveyPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const [helpfulness, setHelpfulness] = useState<number | null>(null)
  const [easeOfUse, setEaseOfUse] = useState<number | null>(null)
  const [questionDifficulty, setQuestionDifficulty] = useState<number | null>(null)
  const [wouldUseAgain, setWouldUseAgain] = useState<boolean | null>(null)
  const [liked, setLiked] = useState('')
  const [disliked, setDisliked] = useState('')
  const [improvements, setImprovements] = useState('')
  const [anythingElse, setAnythingElse] = useState('')
  const [responseFeedback, setResponseFeedback] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const doneUrl = useMemo(() => ROUTE_PATH.STUDENT_DONE, [])

  useEffect(() => {
    if (!sessionId) return
    void studentStudyGuideApi.logClientEvent(sessionId, { type: 'survey_page_viewed', data: {} })
  }, [sessionId])

  const handleSkip = async () => {
    if (submitting) return
    setError(null)
    setSubmitting(true)
    try {
      if (sessionId) {
        await studentStudyGuideApi.logClientEvent(sessionId, { type: 'survey_skipped_clicked', data: {} })
        await studentStudyGuideApi.markStudySurveyCompleted(sessionId, { skipped: true })
      }
    } catch {
      // Best-effort: never block the student on a network hiccup.
    } finally {
      navigate(doneUrl, { replace: true })
    }
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (submitting) return

    if (
      helpfulness === null ||
      easeOfUse === null ||
      questionDifficulty === null ||
      wouldUseAgain === null
    ) {
      setError('Please answer every rating question before submitting.')
      return
    }

    setError(null)
    setSubmitting(true)
    try {
      if (sessionId) {
        await studentStudyGuideApi.logClientEvent(sessionId, { type: 'survey_submit_clicked', data: {} })
        await studentStudyGuideApi.submitExitSurvey(sessionId, {
          helpfulness,
          ease_of_use: easeOfUse,
          question_difficulty: questionDifficulty,
          would_use_again: wouldUseAgain,
          liked,
          disliked,
          improvements,
          anything_else: anythingElse,
          response_feedback: responseFeedback,
        })
        await studentStudyGuideApi.markStudySurveyCompleted(sessionId)
      }
    } catch {
      // Best-effort: never block the student on a network hiccup.
    } finally {
      navigate(doneUrl, { replace: true })
    }
  }

  if (!sessionId) {
    return (
      <main className={styles.page}>
        <p className={styles.hint} role="alert">
          Missing session id.
        </p>
      </main>
    )
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <p className={styles.kicker}>Quick exit survey</p>
        <h1 className={styles.title}>How was your session?</h1>
        <p className={styles.subtitle}>
          This survey is optional. If you choose to submit it, please answer every rating question.
        </p>
      </header>

      <form className={styles.card} onSubmit={handleSubmit} aria-label="Study session exit survey">
        <RatingField
          id="q-helpfulness"
          label="Q1. Helpfulness"
          name="helpfulness"
          value={helpfulness}
          onChange={setHelpfulness}
          leftLabel="1 = not helpful"
          rightLabel="5 = very helpful"
        />
        <RatingField
          id="q-ease"
          label="Q2. Ease of use"
          name="ease_of_use"
          value={easeOfUse}
          onChange={setEaseOfUse}
          leftLabel="1 = hard to use"
          rightLabel="5 = very easy"
        />
        <RatingField
          id="q-difficulty"
          label="Q3. Question difficulty"
          name="question_difficulty"
          value={questionDifficulty}
          onChange={setQuestionDifficulty}
          leftLabel="1 = very easy"
          rightLabel="5 = very difficult"
        />
        <YesNoField
          id="q-use-again"
          label="Q4. Would use again"
          name="would_use_again"
          value={wouldUseAgain}
          onChange={setWouldUseAgain}
          prompt="Would you use it again?"
        />
        <TextField
          id="q-liked"
          label="Q5. What you liked"
          prompt="What did you like about this session?"
          value={liked}
          onChange={setLiked}
          placeholder="Share anything that worked well for you..."
        />
        <TextField
          id="q-disliked"
          label="Q6. What you didn't like"
          prompt="What did you hate or find frustrating?"
          value={disliked}
          onChange={setDisliked}
          placeholder="Share anything that felt frustrating..."
        />
        <TextField
          id="q-improvements"
          label="Q7. What would have helped"
          prompt="What would have made this session better for you today?"
          value={improvements}
          onChange={setImprovements}
          placeholder="Share any suggestions that would have helped..."
        />
        <TextField
          id="q-anything-else"
          label="Q8. Anything else we should know"
          prompt="Anything else we should know about your experience today?"
          value={anythingElse}
          onChange={setAnythingElse}
          placeholder="Share any final thoughts..."
        />
        <TextField
          id="q-response-feedback"
          label="Q9. Response quality"
          prompt="How did you find the responses? Were they too vague, unclear, too detailed, or otherwise unhelpful?"
          value={responseFeedback}
          onChange={setResponseFeedback}
          placeholder="Share how the AI responses felt to you..."
        />

        {error ? (
          <p className={styles.error} role="alert">
            {error}
          </p>
        ) : null}

        <div className={styles.footer}>
          <button
            type="button"
            className={styles.skipButton}
            disabled={submitting}
            data-testid="survey-skip"
            onClick={handleSkip}
          >
            Skip survey
          </button>
          <button
            type="submit"
            className={styles.submitButton}
            disabled={submitting}
            data-testid="survey-submit"
          >
            {submitting ? 'Submitting…' : 'Submit survey'}
          </button>
        </div>
      </form>
    </main>
  )
}
