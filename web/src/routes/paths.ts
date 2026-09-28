// Centralized route constants keep path usage consistent across app and tests.
export const ROUTE_PATH = {
  HOME: '/',
  TEACHER_LEGACY_HOME: '/home',
  TEACHER_LOGIN: '/teacher/login',
  TEACHER_HOME: '/teacher',
  TEACHER_ASSESSMENTS: '/teacher/assessments',
  TEACHER_STUDY_DASHBOARD: '/teacher/study-dashboard',
  TEACHER_CREATE_EXAM: '/teacher/assessments/new',
  TEACHER_ASSESSMENT_DETAIL: '/teacher/assessments/:assessmentId',
  TEACHER_SESSION_DETAIL: '/teacher/sessions/:sessionId',
  TEACHER_REVIEW: '/teacher/review',
  TEACHER_FEEDBACK: '/teacher/feedback',
  TEACHER_FEEDBACK_SUBMITTED: '/teacher/feedback-submitted',
  TEACHER_DONE: '/teacher/done',
  STUDENT_HOME: '/student',
  STUDENT_ASSESSMENTS: '/student/assessments',
  STUDENT_PREP: '/student/prep',
  STUDENT_SESSION: '/student/session',
  STUDENT_STUDY_PREP: '/student/study/prep',
  STUDENT_STUDY_ID: '/student/study/id',
  STUDENT_STUDY_CONFIG: '/student/study/config',
  STUDENT_STUDY_SESSION: '/student/study/session',
  // Post-session feedback page after a student ends a study run.
  // ``:sessionId`` matches the central session id created by Jetson + central.
  STUDENT_STUDY_REVIEW: '/student/study/review/:sessionId',
  STUDENT_STUDY_POST_SESSION: '/student/study/post-session/:sessionId',
  // Optional 5-question exit survey that slots between review and done.
  // Empty submissions skip the POST and go straight to the done page.
  STUDENT_STUDY_SURVEY: '/student/study/survey/:sessionId',
  STUDENT_DONE: '/student/done',
} as const

export type RoutePath = (typeof ROUTE_PATH)[keyof typeof ROUTE_PATH]
