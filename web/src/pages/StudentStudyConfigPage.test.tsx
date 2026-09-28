// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.hoisted(() => {
  vi.stubEnv('VITE_CENTRAL_API_BASE_URL', 'http://central.test')
})

import { ROUTE_PATH } from '../routes/paths'
import { StudentStudyConfigPage } from './StudentStudyConfigPage'

vi.mock('../api/questionBank', () => ({
  questionBankApi: {
    listCourses: vi.fn(),
    listTopics: vi.fn(),
    selectQuestions: vi.fn(),
    listSeenQuestions: vi.fn(),
  },
}))

vi.mock('../api/studentStudyGuide', () => ({
  studentStudyGuideApi: {
    createRun: vi.fn(),
  },
}))

import { studentStudyGuideApi } from '../api/studentStudyGuide'
import { questionBankApi } from '../api/questionBank'

const mockedCreateRun = vi.mocked(studentStudyGuideApi.createRun)
const mockedListCourses = vi.mocked(questionBankApi.listCourses)
const mockedListTopics = vi.mocked(questionBankApi.listTopics)
const mockedSelectQuestions = vi.mocked(questionBankApi.selectQuestions)
const mockedListSeenQuestions = vi.mocked(questionBankApi.listSeenQuestions)

function renderConfig(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={ROUTE_PATH.STUDENT_STUDY_CONFIG} element={<StudentStudyConfigPage />} />
        <Route path={ROUTE_PATH.STUDENT_STUDY_ID} element={<div data-testid="id-page">id</div>} />
        <Route path={ROUTE_PATH.STUDENT_STUDY_SESSION} element={<div data-testid="session-page">session</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
  window.sessionStorage.clear()
})

beforeEach(() => {
  mockedListCourses.mockResolvedValue([])
  mockedListTopics.mockResolvedValue([])
  mockedListSeenQuestions.mockResolvedValue([])
})

describe('StudentStudyConfigPage student ID flow', () => {
  it('passes query-string studentId into study run creation', async () => {
    mockedCreateRun.mockResolvedValue({ sessionId: 'sess-2101' })
    renderConfig('/student/study/config?assessmentId=42&studentId=2101')

    fireEvent.click(screen.getByRole('button', { name: /start practice/i }))

    await waitFor(() => {
      expect(mockedCreateRun).toHaveBeenCalledWith({
        assessmentId: '42',
        studentId: '2101',
      })
    })
    expect(window.sessionStorage.getItem('study:studentId:sess-2101')).toBe('2101')
  })

  it('falls back to the stored studentId when the query string omits it', async () => {
    window.sessionStorage.setItem('study:studentId', '2102')
    mockedCreateRun.mockResolvedValue({ sessionId: 'sess-2102' })
    renderConfig('/student/study/config?assessmentId=42')

    fireEvent.click(screen.getByRole('button', { name: /start practice/i }))

    await waitFor(() => {
      expect(mockedCreateRun).toHaveBeenCalledWith({
        assessmentId: '42',
        studentId: '2102',
      })
    })
  })

  it('redirects to the student ID page when no valid ID is available', async () => {
    renderConfig('/student/study/config?assessmentId=42')

    await waitFor(() => {
      expect(screen.getByTestId('id-page')).toBeInTheDocument()
    })
    expect(mockedCreateRun).not.toHaveBeenCalled()
  })
})

describe('StudentStudyConfigPage question-bank review flow', () => {
  it('passes the student ID when selecting new unseen questions', async () => {
    mockedListCourses.mockResolvedValue([{ id: 'CS109', title: 'CS109 - question bank' }])
    mockedListTopics.mockResolvedValue([{ id: 't1', name: 'Topic 1' }])
    mockedSelectQuestions.mockResolvedValue([
      {
        id: 'new_1',
        text: 'New question?',
        rubric_items: ['Rubric item'],
        difficulty: 'medium',
        hints: [],
      },
    ])
    mockedCreateRun.mockResolvedValue({ sessionId: 'sess-new' })
    renderConfig('/student/study/config?assessmentId=42&studentId=2101')

    fireEvent.change(await screen.findByLabelText(/course/i), { target: { value: 'CS109' } })
    await screen.findByLabelText(/topic/i)
    fireEvent.click(screen.getByRole('button', { name: /start practice/i }))

    await waitFor(() => {
      expect(mockedSelectQuestions).toHaveBeenCalledWith('CS109', 't1', 3, '2101')
    })
  })

  it('shows previously seen questions for review', async () => {
    mockedListCourses.mockResolvedValue([{ id: 'CS109', title: 'CS109 - question bank' }])
    mockedListTopics.mockResolvedValue([{ id: 't1', name: 'Topic 1' }])
    mockedListSeenQuestions.mockResolvedValue([
      {
        id: 'seen_1',
        text: 'Previously seen question?',
        rubric_items: ['Rubric item'],
        difficulty: 'medium',
        hints: [],
      },
    ])
    renderConfig('/student/study/config?assessmentId=42&studentId=2101')

    fireEvent.change(await screen.findByLabelText(/course/i), { target: { value: 'CS109' } })

    expect(await screen.findByText('Previously seen question?')).toBeInTheDocument()
    expect(mockedListSeenQuestions).toHaveBeenCalledWith('CS109', '2101', 't1')
  })

  it('can start a review run from selected previous questions', async () => {
    mockedListCourses.mockResolvedValue([{ id: 'CS109', title: 'CS109 - question bank' }])
    mockedListTopics.mockResolvedValue([{ id: 't1', name: 'Topic 1' }])
    mockedListSeenQuestions.mockResolvedValue([
      {
        id: 'seen_1',
        text: 'Previously seen question?',
        rubric_items: ['Rubric item'],
        difficulty: 'medium',
        hints: ['Hint'],
      },
    ])
    mockedCreateRun.mockResolvedValue({ sessionId: 'sess-review' })
    renderConfig('/student/study/config?assessmentId=42&studentId=2101')

    fireEvent.change(await screen.findByLabelText(/course/i), { target: { value: 'CS109' } })
    fireEvent.click(await screen.findByRole('checkbox', { name: /previously seen question/i }))
    fireEvent.click(screen.getByRole('button', { name: /practice selected review questions/i }))

    await waitFor(() => {
      expect(mockedCreateRun).toHaveBeenCalledWith({
        assessmentId: '42',
        studentId: '2101',
        dayRunId: undefined,
        practiceQuestions: [
          {
            id: 'seen_1',
            text: 'Previously seen question?',
            rubric_items: ['Rubric item'],
            difficulty: 'medium',
            hints: ['Hint'],
          },
        ],
        studyPlan: {
          course: 'CS109',
          topic_id: 't1',
          requested_count: 1,
          question_ids: ['seen_1'],
        },
      })
    })
  })
})
