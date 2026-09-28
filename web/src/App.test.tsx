// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest'

import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import App from './App'
import { STUDENT_TOUR_STORAGE_KEY } from './tour/studentTourSteps'

vi.mock('./api/teacher', () => ({
  teacherApi: {
    getAssessments: vi.fn().mockResolvedValue([
      {
        id: 'assessment-1',
        title: 'Practice Exam',
        totalSessions: 0,
        unreviewedSessions: 0,
        status: 'published',
      },
    ]),
  },
}))

beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = vi.fn()
})

afterEach(() => {
  cleanup()
  window.localStorage.clear()
  vi.clearAllMocks()
})

function renderAppAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

describe('App student tour integration', () => {
  it('shows the student guide button and opens the first-run tour on student routes', async () => {
    renderAppAt('/student/assessments')

    expect(screen.getByRole('button', { name: /student guide/i })).toBeInTheDocument()
    expect(await screen.findByRole('dialog')).toHaveTextContent('Start with study mode')
  })

  it('does not auto-open completed route tours but allows replay from the header', async () => {
    window.localStorage.setItem(
      STUDENT_TOUR_STORAGE_KEY,
      JSON.stringify({ completedRouteKeys: ['student-assessments'] }),
    )

    renderAppAt('/student/assessments')

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /student guide/i }))

    expect(await screen.findByRole('dialog')).toHaveTextContent('Start with study mode')
  })

  it('hides the student guide button outside student routes', () => {
    renderAppAt('/')

    expect(screen.queryByRole('button', { name: /student guide/i })).not.toBeInTheDocument()
  })

  it('opens the first-run tour on the study config route', async () => {
    window.sessionStorage.setItem('study:studentId', '2101')
    renderAppAt('/student/study/config')

    expect(screen.getByRole('button', { name: /student guide/i })).toBeInTheDocument()
    expect(await screen.findByRole('dialog')).toHaveTextContent('Set up your practice')
  })
})
