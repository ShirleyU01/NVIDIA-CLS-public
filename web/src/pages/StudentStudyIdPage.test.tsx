// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest'

import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

import { ROUTE_PATH } from '../routes/paths'
import { studentsApi } from '../api/students'
import { StudentStudyIdPage } from './StudentStudyIdPage'

vi.mock('../api/students', () => ({
  studentsApi: {
    ensureRegistered: vi.fn().mockResolvedValue(undefined),
  },
}))

function ConfigProbe() {
  const location = useLocation()
  return <div data-testid="config-page">{location.search}</div>
}

function renderAt(path = '/student/study/id?assessmentId=42') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={ROUTE_PATH.STUDENT_STUDY_ID} element={<StudentStudyIdPage />} />
        <Route path={ROUTE_PATH.STUDENT_STUDY_CONFIG} element={<ConfigProbe />} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  window.sessionStorage.clear()
})

describe('StudentStudyIdPage', () => {
  it('renders a numeric student ID prompt', () => {
    renderAt()

    expect(screen.getByRole('heading', { name: /sign in with your student id/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/student id/i)).toBeInTheDocument()
  })

  it('rejects empty or non-numeric student IDs', async () => {
    renderAt()

    fireEvent.click(screen.getByRole('button', { name: /continue/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/positive numeric student id/i)

    fireEvent.change(screen.getByLabelText(/student id/i), { target: { value: 'abc' } })
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/positive numeric student id/i)
  })

  it('stores the ID and preserves assessmentId when navigating to config', async () => {
    renderAt('/student/study/id?assessmentId=99')

    fireEvent.change(screen.getByLabelText(/student id/i), { target: { value: '2101' } })
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))

    await waitFor(() => {
      expect(screen.getByTestId('config-page')).toBeInTheDocument()
    })
    expect(window.sessionStorage.getItem('study:studentId')).toBe('2101')
    expect(screen.getByTestId('config-page')).toHaveTextContent('assessmentId=99')
    expect(screen.getByTestId('config-page')).toHaveTextContent('studentId=2101')
    expect(studentsApi.ensureRegistered).toHaveBeenCalledWith('2101')
  })
})
