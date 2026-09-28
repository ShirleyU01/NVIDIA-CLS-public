import type {
  StudyStudentFeedback,
  StudyTeacherSummary,
} from '../types/studyFeedback'
import styles from './TeacherStudyFeedback.module.css'

/**
 * Teacher-side roll-up of post-session study feedback.
 *
 * Renders two cards:
 *
 * 1. The instructor-facing narrative summary (``teacherSummary``) - short
 *    summary plus two bulleted sections the instructor acts on:
 *    "Areas to Flag" (``flags``) and "Suggested Next Steps" (``action_items``).
 * 2. A mirror of exactly what the student saw on the review page - the
 *    three standardized narrative sections (High-level takeaways, Areas to
 *    improve, Next steps) summarized from the in-session per-capture
 *    feedback.
 *
 * The instructor summary is always rendered above the student mirror so
 * the teacher sees their roll-up first, then the student's view of the
 * same run. Renders nothing (returns ``null``) when both inputs are absent
 * so the teacher session-detail page can drop this in unconditionally.
 */

interface Props {
  studentFeedback: StudyStudentFeedback | null
  teacherSummary: StudyTeacherSummary | null
}

function isMeaningfulSummary(s: StudyTeacherSummary | null): boolean {
  if (!s) return false
  return Boolean(s.summary || s.flags.length || s.action_items.length)
}

function isMeaningfulStudentFeedback(s: StudyStudentFeedback | null): boolean {
  if (!s) return false
  return Boolean(
    s.high_level_takeaways.length ||
      s.areas_to_improve.length ||
      s.next_steps.length,
  )
}

interface StudentSectionProps {
  title: string
  items: string[]
  emptyText: string
  testId: string
}

function StudentSection({ title, items, emptyText, testId }: StudentSectionProps) {
  return (
    <div className={styles.studentSection} data-testid={testId}>
      <p className={styles.studentSectionTitle}>{title}</p>
      {items.length > 0 ? (
        <ul className={styles.studentSectionList}>
          {items.map((item, idx) => (
            <li key={`${testId}-${idx}`}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className={styles.studentSectionEmpty}>{emptyText}</p>
      )}
    </div>
  )
}

export function TeacherStudyFeedback({ studentFeedback, teacherSummary }: Props) {
  const hasSummary = isMeaningfulSummary(teacherSummary)
  const hasStudent = isMeaningfulStudentFeedback(studentFeedback)
  if (!hasSummary && !hasStudent) {
    return null
  }

  return (
    <section className={styles.section} aria-label="Study session feedback">
      <header className={styles.sectionHeader}>
        <h2 className={styles.sectionTitle}>Study session feedback</h2>
        <p className={styles.sectionSubtitle}>
          Generated on the device when the student ended the study run.
        </p>
      </header>

      {hasSummary ? (
        <div className={styles.card}>
          <h3 className={styles.cardTitle}>Instructor summary</h3>
          {teacherSummary?.summary ? (
            <p className={styles.summaryBody}>{teacherSummary.summary}</p>
          ) : (
            <p className={styles.placeholder}>No narrative summary was generated.</p>
          )}

          {teacherSummary && teacherSummary.flags.length > 0 ? (
            <div className={styles.block} data-testid="teacher-areas-to-flag">
              <p className={styles.blockTitle}>Areas to Flag</p>
              <ul className={styles.flagList}>
                {teacherSummary.flags.map((flag, idx) => (
                  <li key={`${flag}-${idx}`} className={styles.flagItem}>
                    {flag}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {teacherSummary && teacherSummary.action_items.length > 0 ? (
            <div className={styles.block} data-testid="teacher-suggested-next-steps">
              <p className={styles.blockTitle}>Suggested Next Steps</p>
              <ol className={styles.actionList}>
                {teacherSummary.action_items.map((item, idx) => (
                  <li key={`${item}-${idx}`}>{item}</li>
                ))}
              </ol>
            </div>
          ) : null}
        </div>
      ) : null}

      {hasStudent && studentFeedback ? (
        <div className={styles.card}>
          <h3 className={styles.cardTitle}>What the student saw</h3>
          {studentFeedback.question ? (
            <p className={styles.questionTitle}>{studentFeedback.question}</p>
          ) : null}
          <StudentSection
            title="High-level takeaways"
            items={studentFeedback.high_level_takeaways}
            emptyText="No high-level takeaways were generated."
            testId="teacher-student-takeaways"
          />
          <StudentSection
            title="Areas to improve"
            items={studentFeedback.areas_to_improve}
            emptyText="No specific gaps were flagged."
            testId="teacher-student-areas"
          />
          <StudentSection
            title="Next steps"
            items={studentFeedback.next_steps}
            emptyText="No next-step suggestions were generated."
            testId="teacher-student-next"
          />
        </div>
      ) : null}
    </section>
  )
}
