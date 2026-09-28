// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest'

import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { ROUTE_PATH } from '../routes/paths'
import { StudentStudyReviewPage } from './StudentStudyReviewPage'

// Mock the API adapter so the component never touches fetch.
vi.mock('../api/studentStudyReview', () => ({
  getStudentStudyReview: vi.fn(),
}))

import { getStudentStudyReview } from '../api/studentStudyReview'

const mockedGet = vi.mocked(getStudentStudyReview)

function renderAt(sessionId: string) {
  const path = ROUTE_PATH.STUDENT_STUDY_REVIEW.replace(':sessionId', sessionId)
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={ROUTE_PATH.STUDENT_STUDY_REVIEW} element={<StudentStudyReviewPage />} />
        <Route
          path={ROUTE_PATH.STUDENT_STUDY_POST_SESSION}
          element={<div data-testid="post-session-page">post-session</div>}
        />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
  window.sessionStorage.clear()
})

describe('StudentStudyReviewPage', () => {
  it('renders the loader while feedback is pending', async () => {
    mockedGet.mockResolvedValue({ status: 'pending', feedback: null })

    renderAt('sess-123')

    expect(await screen.findByTestId('study-review-loader')).toBeInTheDocument()
    expect(screen.getByText(/preparing your feedback/i)).toBeInTheDocument()
  })

  it('renders all three narrative sections with their bullets once feedback is ready', async () => {
    mockedGet.mockResolvedValue({
      status: 'ready',
      feedback: {
        question: 'What is the acceleration?',
        high_level_takeaways: [
          'Set up the free-body diagram correctly.',
          'Solid improvement between capture 1 and capture 2.',
        ],
        areas_to_improve: ['Units dropped in capture 1.'],
        next_steps: [
          'Redo the block problem writing units at every step.',
          'Try a harder variant with friction.',
        ],
      },
    })

    renderAt('sess-456')

    await waitFor(() => {
      expect(screen.getByText('What is the acceleration?')).toBeInTheDocument()
    })

    const takeaways = screen.getByTestId('study-section-takeaways')
    expect(within(takeaways).getByRole('heading', { name: /high-level takeaways/i })).toBeInTheDocument()
    expect(within(takeaways).getByText('Set up the free-body diagram correctly.')).toBeInTheDocument()
    expect(within(takeaways).getByText('Solid improvement between capture 1 and capture 2.')).toBeInTheDocument()

    const areas = screen.getByTestId('study-section-areas')
    expect(within(areas).getByRole('heading', { name: /areas to improve/i })).toBeInTheDocument()
    expect(within(areas).getByText('Units dropped in capture 1.')).toBeInTheDocument()

    const next = screen.getByTestId('study-section-next')
    expect(within(next).getByRole('heading', { name: /next steps/i })).toBeInTheDocument()
    expect(within(next).getByText('Redo the block problem writing units at every step.')).toBeInTheDocument()
    expect(within(next).getByText('Try a harder variant with friction.')).toBeInTheDocument()
  })

  it('routes Finish to the post-session decision page', async () => {
    mockedGet.mockResolvedValue({
      status: 'ready',
      feedback: {
        question: 'Q?',
        high_level_takeaways: ['t'],
        areas_to_improve: [],
        next_steps: [],
      },
    })

    renderAt('sess-finish')

    fireEvent.click(await screen.findByRole('button', { name: /finish/i }))

    await waitFor(() => {
      expect(screen.getByTestId('post-session-page')).toBeInTheDocument()
    })
  })

  it('shows a per-section empty placeholder when a section has no bullets', async () => {
    mockedGet.mockResolvedValue({
      status: 'ready',
      feedback: {
        question: 'Q?',
        high_level_takeaways: ['Some takeaway.'],
        areas_to_improve: [],
        next_steps: [],
      },
    })

    renderAt('sess-789')

    await waitFor(() => {
      expect(screen.getByText('Some takeaway.')).toBeInTheDocument()
    })
    const areas = screen.getByTestId('study-section-areas')
    expect(within(areas).getByText(/no specific gaps were flagged/i)).toBeInTheDocument()
    const next = screen.getByTestId('study-section-next')
    expect(within(next).getByText(/no next-step suggestions/i)).toBeInTheDocument()
  })
})
