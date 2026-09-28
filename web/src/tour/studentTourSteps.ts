import { matchPath } from 'react-router-dom'

import type { GuidedTourStep } from '../components/GuidedTour'
import { ROUTE_PATH } from '../routes/paths'

export const STUDENT_TOUR_STORAGE_KEY = 'socrates:student-tour:v1'

export type StudentTourRouteKey =
  | 'student-assessments'
  | 'student-study-prep'
  | 'student-study-config'
  | 'student-exam-prep'
  | 'student-study-session'
  | 'student-exam-session'
  | 'student-study-review'
  | 'student-done'

type StudentTourRoute = {
  key: StudentTourRouteKey
  pattern: string
  steps: GuidedTourStep[]
}

const studentTourRoutes: StudentTourRoute[] = [
  {
    key: 'student-assessments',
    pattern: ROUTE_PATH.STUDENT_ASSESSMENTS,
    steps: [
      {
        id: 'student-assessments-study',
        selector: '[data-tour="student-study-default"]',
        title: 'Start with study mode',
        body: 'Use Study (default) when you want practice feedback before an exam. It lets you solve on paper, capture your work, and ask for help.',
      },
      {
        id: 'student-assessments-exam',
        selector: '[data-tour="student-exam-mode"]',
        title: 'Use exam mode for assessment',
        body: 'Exam mode starts the oral assessment flow. The system records your spoken answers for your instructor to review.',
      },
    ],
  },
  {
    key: 'student-study-prep',
    pattern: ROUTE_PATH.STUDENT_STUDY_PREP,
    steps: [
      {
        id: 'student-study-prep-begin',
        selector: '[data-tour="student-begin-study"]',
        title: 'Begin a study run',
        body: 'Click Begin Study when you are ready to practice. The next screen shows the problem, camera preview, feedback, and help controls.',
      },
      {
        id: 'student-study-prep-exam-link',
        selector: '[data-tour="student-prep-exam-mode"]',
        title: 'Switch to exam mode',
        body: 'Use this link if you are ready for the full oral exam instead of guided practice.',
      },
    ],
  },
  {
    key: 'student-study-config',
    pattern: ROUTE_PATH.STUDENT_STUDY_CONFIG,
    steps: [
      {
        id: 'student-study-config-intro',
        selector: '[data-tour="student-study-config-intro"]',
        title: 'Set up your practice',
        body: 'Use this page to choose what you want to practice before starting the study session.',
      },
      {
        id: 'student-study-config-bank',
        selector: '[data-tour="student-study-config-bank"]',
        title: 'Choose question-bank practice',
        body: 'If courses are available, select a course to practice from the question bank. Leaving it unchanged uses the assessment question only.',
      },
      {
        id: 'student-study-config-course',
        selector: '[data-tour="student-study-course"]',
        title: 'Pick a course',
        body: 'Choose the course you want to practice. After choosing a course, the page shows topic and question-count options.',
      },
      {
        id: 'student-study-config-start',
        selector: '[data-tour="student-start-practice"]',
        title: 'Start practice',
        body: 'Click Start Practice when your setup looks right. The next screen will show your problem, camera preview, and feedback controls.',
      },
    ],
  },
  {
    key: 'student-exam-prep',
    pattern: ROUTE_PATH.STUDENT_PREP,
    steps: [
      {
        id: 'student-exam-prep-begin',
        selector: '[data-tour="student-begin-exam"]',
        title: 'Begin the oral exam',
        body: 'Click Begin Exam after you have checked the instructions. The system will ask questions and listen for your answers.',
      },
    ],
  },
  {
    key: 'student-study-session',
    pattern: ROUTE_PATH.STUDENT_STUDY_SESSION,
    steps: [
      {
        id: 'student-study-question',
        selector: '[data-tour="student-study-question"]',
        title: 'Read the current problem',
        body: 'This panel shows the problem to solve. Work it out on paper before you capture your answer.',
      },
      {
        id: 'student-study-status',
        selector: '[data-tour="student-study-status"]',
        title: 'Watch the status',
        body: 'The status tells you when the system is ready, capturing, grading, or showing feedback.',
      },
      {
        id: 'student-study-preview',
        selector: '[data-tour="student-study-preview-toggle"]',
        title: 'Control the camera preview',
        body: 'Use the preview button to enable or stop the camera view. Frame your paper inside the guide so your writing is readable.',
      },
      {
        id: 'student-study-capture',
        selector: '[data-tour="student-capture-grade"]',
        title: 'Capture and evaluate your work',
        body: 'Click Capture page to take photos of your work. When you’re done, tap “evaluate” so the system can review a clear photo.',
      },
      {
        id: 'student-study-feedback',
        selector: '[data-tour="student-study-feedback"]',
        title: 'Review feedback here',
        body: 'After grading finishes, feedback appears in this area with the next step to improve your answer.',
      },
      {
        id: 'student-study-understand',
        selector: '[data-tour="student-understand"]',
        title: 'Move on when it makes sense',
        body: 'Click I understand when the feedback is clear and you are ready for the next step.',
      },
      {
        id: 'student-study-lost',
        selector: '[data-tour="student-lost"]',
        title: 'Ask for guided help',
        body: 'Click I’m lost when you need the system to slow down and give more support.',
      },
      {
        id: 'student-study-ask',
        selector: '[data-tour="student-ask-question"]',
        title: 'Ask a specific question',
        body: 'Type a question about a step or concept, then use Ask to get a targeted response.',
      },
      {
        id: 'student-study-end',
        selector: '[data-tour="student-end-study"]',
        title: 'End study mode',
        body: 'Click End Study when you are finished. The app will prepare a summary review page for the session.',
      },
    ],
  },
  {
    key: 'student-exam-session',
    pattern: ROUTE_PATH.STUDENT_SESSION,
    steps: [
      {
        id: 'student-exam-recording',
        selector: '[data-tour="student-recording-status"]',
        title: 'Recording is active',
        body: 'This banner means the exam session is recording your answers for review.',
      },
      {
        id: 'student-exam-question',
        selector: '[data-tour="student-exam-question"]',
        title: 'Answer the current question',
        body: 'Read the question here, then speak your answer clearly. Pauses are okay.',
      },
      {
        id: 'student-exam-transcript',
        selector: '[data-tour="student-transcript"]',
        title: 'Check the transcript',
        body: 'As you speak, the running transcript and key moments appear here.',
      },
      {
        id: 'student-exam-done-speaking',
        selector: '[data-tour="student-done-speaking"]',
        title: 'Tell the system you are done',
        body: 'Click I’m Done after you finish answering. The system will create the next question or follow-up.',
      },
      {
        id: 'student-exam-end',
        selector: '[data-tour="student-end-exam"]',
        title: 'End the exam',
        body: 'Use End Exam only when you are finished with the full assessment.',
      },
    ],
  },
  {
    key: 'student-study-review',
    pattern: ROUTE_PATH.STUDENT_STUDY_REVIEW,
    steps: [
      {
        id: 'student-review-results',
        selector: '[data-tour="student-study-review-results"]',
        title: 'Review your study feedback',
        body: 'This page summarizes how you did after the study run. It may show a loader while feedback is still being prepared.',
      },
      {
        id: 'student-review-finish',
        selector: '[data-tour="student-review-finish"]',
        title: 'Finish the review',
        body: 'Click Finish when you are done reading your feedback.',
      },
    ],
  },
  {
    key: 'student-done',
    pattern: ROUTE_PATH.STUDENT_DONE,
    steps: [
      {
        id: 'student-done-home',
        selector: '[data-tour="student-done-home"]',
        title: 'Return home',
        body: 'This link takes you back to the main page after your student session is complete.',
      },
    ],
  },
]

export function getStudentTourRoute(pathname: string): StudentTourRoute | null {
  return (
    studentTourRoutes.find((route) =>
      matchPath({ path: route.pattern, end: true }, pathname),
    ) ?? null
  )
}

export function isStudentRoute(pathname: string) {
  return pathname.startsWith('/student')
}
