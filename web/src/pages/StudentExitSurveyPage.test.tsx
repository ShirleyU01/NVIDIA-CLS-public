// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest'

import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { ROUTE_PATH } from '../routes/paths'
import { StudentExitSurveyPage } from './StudentExitSurveyPage'

// Mock the API adapter so we can assert whether the page POSTs or not.
vi.mock('../api/studentStudyGuide', () => ({
  studentStudyGuideApi: {
    submitExitSurvey: vi.fn(),
    markStudySurveyCompleted: vi.fn(),
    logClientEvent: vi.fn(),
  },
}))

import { studentStudyGuideApi } from '../api/studentStudyGuide'

const mockedSubmit = vi.mocked(studentStudyGuideApi.submitExitSurvey)
const mockedMarkCompleted = vi.mocked(studentStudyGuideApi.markStudySurveyCompleted)

function renderAt(sessionId: string) {
  const path = ROUTE_PATH.STUDENT_STUDY_SURVEY.replace(':sessionId', sessionId)
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={ROUTE_PATH.STUDENT_STUDY_SURVEY} element={<StudentExitSurveyPage />} />
        <Route path={ROUTE_PATH.STUDENT_DONE} element={<div data-testid="done-page">done</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

describe('StudentExitSurveyPage', () => {
  it('renders all nine questions, a submit button, and a skip button', () => {
    renderAt('sess-render')

    expect(screen.getByText(/Q1\. Helpfulness/i)).toBeInTheDocument()
    expect(screen.getByText(/Q2\. Ease of use/i)).toBeInTheDocument()
    expect(screen.getByText(/Q3\. Question difficulty/i)).toBeInTheDocument()
    expect(screen.getByText(/Q4\. Would use again/i)).toBeInTheDocument()
    expect(screen.getByText(/Q5\. What you liked/i)).toBeInTheDocument()
    expect(screen.getByText(/Q6\. What you didn't like/i)).toBeInTheDocument()
    expect(screen.getByText(/Q7\. What would have helped/i)).toBeInTheDocument()
    expect(screen.getByText(/Q8\. Anything else we should know/i)).toBeInTheDocument()
    expect(screen.getByText(/Q9\. Response quality/i)).toBeInTheDocument()
    expect(screen.getByTestId('rating-helpfulness')).toBeInTheDocument()
    expect(screen.getByTestId('rating-ease_of_use')).toBeInTheDocument()
    expect(screen.getByTestId('rating-question_difficulty')).toBeInTheDocument()
    expect(screen.getByTestId('rating-would_use_again')).toBeInTheDocument()
    expect(screen.getAllByTestId('survey-submit')).toHaveLength(1)
    expect(screen.getAllByTestId('survey-skip')).toHaveLength(1)
    expect(screen.getByText(/this survey is optional/i)).toBeInTheDocument()
  })

  it('empty submit: shows a validation error and does not navigate', async () => {
    renderAt('sess-empty')

    fireEvent.click(screen.getByTestId('survey-submit'))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/please answer every rating question/i)
    })
    expect(mockedSubmit).not.toHaveBeenCalled()
    expect(mockedMarkCompleted).not.toHaveBeenCalled()
  })

  it('short or empty written responses: submits after required rating questions are answered', async () => {
    mockedSubmit.mockResolvedValue(undefined)
    mockedMarkCompleted.mockResolvedValue(undefined)
    renderAt('sess-short-ok')

    fireEvent.click(screen.getByRole('radio', { name: /Q1\. Helpfulness: 4/i }))
    fireEvent.click(screen.getByRole('radio', { name: /Q2\. Ease of use: 3/i }))
    fireEvent.click(screen.getByRole('radio', { name: /Q3\. Question difficulty: 2/i }))
    fireEvent.click(screen.getByRole('radio', { name: /Q4\. Would use again: Yes/i }))
    fireEvent.change(screen.getByRole('textbox', { name: /what did you like about this session/i }), {
      target: { value: 'Ok.' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: /what did you hate or find frustrating/i }), {
      target: { value: '' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: /what would have made this session better for you today/i }), {
      target: { value: 'More examples.' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: /anything else we should know about your experience today/i }), {
      target: { value: '' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: /how did you find the responses/i }), {
      target: { value: 'Too vague.' },
    })

    fireEvent.click(screen.getByTestId('survey-submit'))

    await waitFor(() => {
      expect(mockedSubmit).toHaveBeenCalledTimes(1)
    })
    expect(mockedSubmit).toHaveBeenCalledWith('sess-short-ok', {
      helpfulness: 4,
      ease_of_use: 3,
      question_difficulty: 2,
      would_use_again: true,
      liked: 'Ok.',
      disliked: '',
      improvements: 'More examples.',
      anything_else: '',
      response_feedback: 'Too vague.',
    })
    expect(mockedMarkCompleted).toHaveBeenCalledWith('sess-short-ok')
    await waitFor(() => {
      expect(screen.getByTestId('done-page')).toBeInTheDocument()
    })
  })

  it('complete submit: POSTs all required fields, marks completion, then navigates to Done', async () => {
    mockedSubmit.mockResolvedValue(undefined)
    mockedMarkCompleted.mockResolvedValue(undefined)
    renderAt('sess-complete')

    fireEvent.click(screen.getByRole('radio', { name: /Q1\. Helpfulness: 4/i }))
    fireEvent.click(screen.getByRole('radio', { name: /Q2\. Ease of use: 5/i }))
    fireEvent.click(screen.getByRole('radio', { name: /Q3\. Question difficulty: 3/i }))
    fireEvent.click(screen.getByRole('radio', { name: /Q4\. Would use again: Yes/i }))
    fireEvent.change(
      screen.getByRole('textbox', { name: /what did you like about this session/i }),
      { target: { value: 'The instant feedback was very helpful and easy to understand for me.' } },
    )
    fireEvent.change(
      screen.getByRole('textbox', { name: /what did you hate or find frustrating/i }),
      { target: { value: 'The camera framing felt a little awkward at first and took some practice.' } },
    )
    fireEvent.change(
      screen.getByRole('textbox', { name: /what would have made this session better for you today/i }),
      { target: { value: 'I would like clearer examples and more guidance before the first question starts.' } },
    )
    fireEvent.change(
      screen.getByRole('textbox', { name: /anything else we should know about your experience today/i }),
      { target: { value: 'I appreciated the tool overall and would be interested in trying it again in class.' } },
    )
    fireEvent.change(
      screen.getByRole('textbox', { name: /how did you find the responses/i }),
      { target: { value: 'The responses were clear overall and only occasionally felt a little too broad.' } },
    )

    fireEvent.click(screen.getByTestId('survey-submit'))

    await waitFor(() => {
      expect(mockedSubmit).toHaveBeenCalledTimes(1)
    })
    expect(mockedSubmit).toHaveBeenCalledWith('sess-complete', {
      helpfulness: 4,
      ease_of_use: 5,
      question_difficulty: 3,
      would_use_again: true,
      liked: 'The instant feedback was very helpful and easy to understand for me.',
      disliked: 'The camera framing felt a little awkward at first and took some practice.',
      improvements: 'I would like clearer examples and more guidance before the first question starts.',
      anything_else: 'I appreciated the tool overall and would be interested in trying it again in class.',
      response_feedback: 'The responses were clear overall and only occasionally felt a little too broad.',
    })
    expect(mockedMarkCompleted).toHaveBeenCalledWith('sess-complete')
    await waitFor(() => {
      expect(screen.getByTestId('done-page')).toBeInTheDocument()
    })
  })

  it('network failure: still navigates to Done and does not re-throw', async () => {
    mockedSubmit.mockRejectedValue(new Error('network down'))
    renderAt('sess-neterr')

    fireEvent.click(screen.getByRole('radio', { name: /Q1\. Helpfulness: 4/i }))
    fireEvent.click(screen.getByRole('radio', { name: /Q2\. Ease of use: 3/i }))
    fireEvent.click(screen.getByRole('radio', { name: /Q3\. Question difficulty: 2/i }))
    fireEvent.click(screen.getByRole('radio', { name: /Q4\. Would use again: No/i }))
    fireEvent.change(screen.getByRole('textbox', { name: /what did you like about this session/i }), {
      target: { value: 'The session was helpful overall and the explanations were easy to follow.' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: /what did you hate or find frustrating/i }), {
      target: { value: 'The first capture took a bit too long and made me unsure at the beginning.' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: /what would have made this session better for you today/i }), {
      target: { value: 'I wanted a faster onboarding and more examples before starting the practice.' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: /anything else we should know about your experience today/i }), {
      target: { value: 'The concept is promising and I would like to compare it against normal office hours.' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: /how did you find the responses/i }), {
      target: { value: 'The responses were mostly helpful, though sometimes I wanted more precise details.' },
    })
    fireEvent.click(screen.getByTestId('survey-submit'))

    await waitFor(() => {
      expect(mockedSubmit).toHaveBeenCalledTimes(1)
    })
    expect(mockedMarkCompleted).not.toHaveBeenCalled()
    await waitFor(() => {
      expect(screen.getByTestId('done-page')).toBeInTheDocument()
    })
  })

  it('completion marker failure: still navigates to Done', async () => {
    mockedSubmit.mockResolvedValue(undefined)
    mockedMarkCompleted.mockRejectedValue(new Error('central down'))
    renderAt('sess-marker-fail')

    fireEvent.click(screen.getByRole('radio', { name: /Q1\. Helpfulness: 5/i }))
    fireEvent.click(screen.getByRole('radio', { name: /Q2\. Ease of use: 4/i }))
    fireEvent.click(screen.getByRole('radio', { name: /Q3\. Question difficulty: 3/i }))
    fireEvent.click(screen.getByRole('radio', { name: /Q4\. Would use again: Yes/i }))
    fireEvent.change(screen.getByRole('textbox', { name: /what did you like about this session/i }), {
      target: { value: 'I liked how quickly the system gave me targeted feedback on my work.' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: /what did you hate or find frustrating/i }), {
      target: { value: 'Sometimes the setup felt a bit clunky before I understood the capture flow.' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: /what would have made this session better for you today/i }), {
      target: { value: 'A more obvious tutorial and clearer instructions would have helped me a lot.' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: /anything else we should know about your experience today/i }), {
      target: { value: 'I think this could be really useful for exam prep once the workflow feels more polished.' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: /how did you find the responses/i }), {
      target: { value: 'The responses felt encouraging and usually specific enough for my written work.' },
    })
    fireEvent.click(screen.getByTestId('survey-submit'))

    await waitFor(() => {
      expect(mockedMarkCompleted).toHaveBeenCalledWith('sess-marker-fail')
    })
    await waitFor(() => {
      expect(screen.getByTestId('done-page')).toBeInTheDocument()
    })
  })

  it('skip survey: marks completion as skipped, does not submit answers, and navigates to Done', async () => {
    mockedMarkCompleted.mockResolvedValue(undefined)
    renderAt('sess-skip')

    fireEvent.click(screen.getByTestId('survey-skip'))

    await waitFor(() => {
      expect(mockedMarkCompleted).toHaveBeenCalledWith('sess-skip', { skipped: true })
    })
    expect(mockedSubmit).not.toHaveBeenCalled()
    await waitFor(() => {
      expect(screen.getByTestId('done-page')).toBeInTheDocument()
    })
  })

  it('skip marker failure: still navigates to Done', async () => {
    mockedMarkCompleted.mockRejectedValue(new Error('central down'))
    renderAt('sess-skip-fail')

    fireEvent.click(screen.getByTestId('survey-skip'))

    await waitFor(() => {
      expect(mockedMarkCompleted).toHaveBeenCalledWith('sess-skip-fail', { skipped: true })
    })
    expect(mockedSubmit).not.toHaveBeenCalled()
    await waitFor(() => {
      expect(screen.getByTestId('done-page')).toBeInTheDocument()
    })
  })
})
