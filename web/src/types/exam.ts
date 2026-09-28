export type ExamStatus = 'idle' | 'listening' | 'speaking' | 'thinking' | 'done'

export interface ExamState {
  sessionId: string
  status: ExamStatus
  questionText: string
  transcriptPreview: string
}

