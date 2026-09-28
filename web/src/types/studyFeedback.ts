/**
 * TypeScript mirrors of the Python study-mode feedback contracts in
 * ``jetson_runtime/study_guide/feedback_contracts.py``.
 *
 * The shapes here are what the central backend's ``GET /sessions/:id``
 * exposes under the ``study_feedback`` and ``study_teacher_summary`` keys.
 * Both sides use the same defensive defaults: missing data is null/empty,
 * not "undefined behavior".
 *
 * The student-facing post-session report is a summarization of the
 * in-session per-capture feedback, organized into three standardized
 * bulleted sections.
 */

export interface StudyStudentFeedback {
  question: string
  high_level_takeaways: string[]
  areas_to_improve: string[]
  next_steps: string[]
}

/**
 * Kept as an alias so existing callers that imported the union type keep
 * compiling after v2 was removed; there is only one student shape now.
 */
export type StudyStudentFeedbackAny = StudyStudentFeedback

export interface StudyTeacherSummary {
  summary: string
  flags: string[]
  action_items: string[]
}
