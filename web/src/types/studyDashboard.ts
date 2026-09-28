export type StudyDashboardTotals = {
  sessions: number
  studySessionsStarted: number
  students: number
  activatedSessions: number
  activationRate: number
  completedSessions: number
  completionRate: number
  reachedPostSessionSummaryCount: number
  reachedPostSessionSummaryRate: number
  surveySubmissions: number
  surveySubmitRate: number
  repeatedUsageYesCount: number
  repeatedUsageResponseCount: number
  repeatedUsageRate: number | null
  avgHelpfulness: number | null
  avgEaseOfUse: number | null
  avgQuestionDifficulty: number | null
  avgSessionDurationMs: number | null
  avgGradeDurationMs: number | null
  avgTimeToFirstCaptureMs: number | null
  avgTimeWorkingMs: number | null
  avgQuestionsPerSession: number | null
  avgPercentCorrectQuestions: number | null
  jetsonBackendErrorRate: number | null
  totalQuestions: number
  totalCaptures: number
  totalAmaTurns: number
  backendErrorCount: number
  clientErrorCount: number
  questionsAnsweredOral: number
  questionsAnsweredPaper: number
  oralUploadCount: number
  oralTranscriptCount: number
  oralRetakeCount: number
  oralRecordStartedCount: number
  avgOralRecordDurationMs: number | null
  avgTranscriptionDurationMs: number | null
  p95TranscriptionDurationMs: number | null
  avgUploadToTranscriptMs: number | null
  avgPaperGradeDurationMs: number | null
  avgOralGradeDurationMs: number | null
  p95OralGradeDurationMs: number | null
  oralTranscriptTotalChars: number
}

export type StudyDashboardSessionRow = {
  sessionId: string
  studentId: string
  dayRunId: string
  course: string
  topicId: string
  requestedCount: number | null
  eventCount: number
  studySessionsStarted: number
  questionCount: number
  captureCount: number
  activated: boolean
  amaUserCount: number
  gradeCount: number
  sessionCompleted: boolean
  reachedPostSessionSummary: boolean
  surveySubmitted: boolean
  surveyHelpfulness: number | null
  surveyEaseOfUse: number | null
  surveyQuestionDifficulty: number | null
  surveyWouldUseAgain: boolean | null
  surveyLiked: string
  surveyDisliked: string
  surveyImprovements: string
  surveyAnythingElse: string
  surveyResponseFeedback: string
  sessionDurationMs: number | null
  avgGradeDurationMs: number | null
  timeToFirstCaptureMs: number | null
  avgTimeWorkingMs: number | null
  percentCorrectQuestions: number | null
  questionsWithRepeatAttempts: number
  backendErrorCount: number
  clientErrorCount: number
  jetsonBackendErrorRate: number | null
  questionsAnsweredOral: number
  questionsAnsweredPaper: number
  oralUploadCount: number
  oralTranscriptCount: number
  oralRetakeCount: number
  oralRecordStartedCount: number
  avgOralRecordDurationMs: number | null
  avgTranscriptionDurationMs: number | null
  uploadToTranscriptMs: number | null
  avgPaperGradeDurationMs: number | null
  avgOralGradeDurationMs: number | null
  oralTranscriptTotalChars: number
}

export type StudyDashboardTopicRow = {
  course: string
  topicId: string
  sessions: number
  completionRate: number
  avgHelpfulness: number | null
  avgPercentCorrectQuestions: number | null
  avgGradeDurationMs: number | null
  questionsAnsweredOral: number
  questionsAnsweredPaper: number
  oralTranscriptCount: number
  avgTranscriptionDurationMs: number | null
  avgOralGradeDurationMs: number | null
}

export type StudyDashboardSummary = {
  generatedAt: string
  sourceRoot: string
  totals: StudyDashboardTotals
  sessions: StudyDashboardSessionRow[]
  topics: StudyDashboardTopicRow[]
  malformedFiles: number
}
