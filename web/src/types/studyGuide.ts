export type StudyStatus = 'idle' | 'capturing' | 'thinking' | 'done' | 'error'

export type StudyAnswerMode = 'paper' | 'oral'

export interface StudyAmaTurn {
  role: string
  content: string
}

export interface StudyRunState {
  sessionId: string
  status: StudyStatus
  questionText: string
  feedbackMarkdown: string
  followUpMarkdown: string
  latestImageUrl: string
  error: string
  captureCount: number
  captureLimit: number
  questionIndex: number
  questionCount: number
  hints: string[]
  /** Tutor chat turns (from Jetson); grows through the session. */
  amaTurns: StudyAmaTurn[]
  /** How the student submits work for the current question. */
  answerMode: StudyAnswerMode
  /** STT transcript for the current question (oral mode). */
  oralTranscript: string
  oralHasRecording: boolean
}
