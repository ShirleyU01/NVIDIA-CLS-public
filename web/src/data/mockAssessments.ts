import type { AssessmentSummary, GradeBucket, SessionSummary } from '../types/assessment'

export const mockAssessments: AssessmentSummary[] = [
  {
    id: 'bayes-oral-v1',
    title: "Bayes' Rule Oral Exam",
    totalSessions: 12,
    unreviewedSessions: 3,
  },
  {
    id: 'big-o-oral-v1',
    title: 'Big-O Complexity Oral Exam',
    totalSessions: 5,
    unreviewedSessions: 1,
  },
]

export const mockGradeBucketsByAssessment: Record<string, GradeBucket[]> = {
  'bayes-oral-v1': [
    { label: 'A', count: 4 },
    { label: 'B', count: 5 },
    { label: 'C', count: 2 },
    { label: 'D', count: 1 },
  ],
  'big-o-oral-v1': [
    { label: 'A', count: 1 },
    { label: 'B', count: 2 },
    { label: 'C', count: 1 },
    { label: 'D', count: 1 },
  ],
}

export const mockSessions: SessionSummary[] = [
  {
    id: 'sess-001',
    assessmentId: 'bayes-oral-v1',
    studentName: 'Student A',
    dateIso: '2026-03-01T10:00:00Z',
    status: 'reviewed',
    score: 5.5,
  },
  {
    id: 'sess-002',
    assessmentId: 'bayes-oral-v1',
    studentName: 'Student B',
    dateIso: '2026-03-01T11:00:00Z',
    status: 'ready',
    score: 6.0,
  },
  {
    id: 'sess-003',
    assessmentId: 'bayes-oral-v1',
    studentName: 'Student C',
    dateIso: '2026-03-02T09:30:00Z',
    status: 'pending',
    score: null,
  },
  {
    id: 'sess-101',
    assessmentId: 'big-o-oral-v1',
    studentName: 'Student D',
    dateIso: '2026-03-03T14:15:00Z',
    status: 'ready',
    score: 6.5,
  },
]

