export type TeacherReviewSummary = {
  instructorName: string
  summaryTitle: string
  summaryBody: string
  suggestedGrade: string
}

// Backwards-compatible alias (if older components still import this name).
export type TeacherReviewData = TeacherReviewSummary
