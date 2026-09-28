// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest'

import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'

import { TeacherStudyFeedback } from './TeacherStudyFeedback'

afterEach(() => {
  cleanup()
})

describe('TeacherStudyFeedback', () => {
  it('renders the teacher summary plus the three student narrative sections when populated', () => {
    render(
      <TeacherStudyFeedback
        teacherSummary={{
          summary: 'Strong derivation, weak units.',
          flags: ['unit confusion', 'rushed step 3'],
          action_items: ['Re-teach unit conversion', 'Practice block 4'],
        }}
        studentFeedback={{
          question: 'What is the acceleration?',
          high_level_takeaways: [
            'Free-body diagram was set up correctly.',
            'Solid recovery in capture 2.',
          ],
          areas_to_improve: ['Units dropped in capture 1.'],
          next_steps: ['Redo the block problem writing units at every step.'],
        }}
      />,
    )

    expect(screen.getByText('Study session feedback')).toBeInTheDocument()

    // Teacher narrative is unchanged.
    expect(screen.getByText('Strong derivation, weak units.')).toBeInTheDocument()

    // The two instructor bullet sections use the agreed labels.
    const flagged = screen.getByTestId('teacher-areas-to-flag')
    expect(within(flagged).getByText('Areas to Flag')).toBeInTheDocument()
    expect(within(flagged).getByText('unit confusion')).toBeInTheDocument()
    expect(within(flagged).getByText('rushed step 3')).toBeInTheDocument()

    const nextSteps = screen.getByTestId('teacher-suggested-next-steps')
    expect(within(nextSteps).getByText('Suggested Next Steps')).toBeInTheDocument()
    expect(within(nextSteps).getByText('Re-teach unit conversion')).toBeInTheDocument()
    expect(within(nextSteps).getByText('Practice block 4')).toBeInTheDocument()

    // Student mirror shows the three new sections, not a per-rubric table.
    expect(screen.getByText('What is the acceleration?')).toBeInTheDocument()

    const takeaways = screen.getByTestId('teacher-student-takeaways')
    expect(within(takeaways).getByText(/high-level takeaways/i)).toBeInTheDocument()
    expect(within(takeaways).getByText('Free-body diagram was set up correctly.')).toBeInTheDocument()
    expect(within(takeaways).getByText('Solid recovery in capture 2.')).toBeInTheDocument()

    const areas = screen.getByTestId('teacher-student-areas')
    expect(within(areas).getByText(/areas to improve/i)).toBeInTheDocument()
    expect(within(areas).getByText('Units dropped in capture 1.')).toBeInTheDocument()

    const next = screen.getByTestId('teacher-student-next')
    expect(within(next).getByText(/next steps/i)).toBeInTheDocument()
    expect(within(next).getByText('Redo the block problem writing units at every step.')).toBeInTheDocument()
  })

  it('renders nothing when both inputs are null', () => {
    const { container } = render(
      <TeacherStudyFeedback teacherSummary={null} studentFeedback={null} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when both inputs are empty (no summary, no narrative sections, no flags)', () => {
    const { container } = render(
      <TeacherStudyFeedback
        teacherSummary={{ summary: '', flags: [], action_items: [] }}
        studentFeedback={{
          question: '',
          high_level_takeaways: [],
          areas_to_improve: [],
          next_steps: [],
        }}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('renders only the teacher summary section when student feedback is null', () => {
    render(
      <TeacherStudyFeedback
        teacherSummary={{
          summary: 'Just a teacher summary',
          flags: [],
          action_items: [],
        }}
        studentFeedback={null}
      />,
    )
    expect(screen.getByText('Just a teacher summary')).toBeInTheDocument()
    // Student mirror card should NOT render.
    expect(screen.queryByText(/What the student saw/i)).not.toBeInTheDocument()
    expect(screen.queryByTestId('teacher-student-takeaways')).not.toBeInTheDocument()
  })

  it('renders empty placeholders per-section when the student feedback has a mix of populated and empty sections', () => {
    render(
      <TeacherStudyFeedback
        teacherSummary={null}
        studentFeedback={{
          question: 'Q?',
          high_level_takeaways: ['A takeaway.'],
          areas_to_improve: [],
          next_steps: [],
        }}
      />,
    )
    expect(screen.getByText('A takeaway.')).toBeInTheDocument()
    const areas = screen.getByTestId('teacher-student-areas')
    expect(within(areas).getByText(/no specific gaps/i)).toBeInTheDocument()
    const next = screen.getByTestId('teacher-student-next')
    expect(within(next).getByText(/no next-step suggestions/i)).toBeInTheDocument()
  })
})
