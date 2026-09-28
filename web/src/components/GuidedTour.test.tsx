// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest'

import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import { GuidedTour, type GuidedTourStep } from './GuidedTour'

const steps: GuidedTourStep[] = [
  {
    id: 'one',
    selector: '[data-tour="first"]',
    title: 'First control',
    body: 'This is the first thing to know.',
  },
  {
    id: 'two',
    selector: '[data-tour="second"]',
    title: 'Second control',
    body: 'This is the second thing to know.',
  },
]

beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = vi.fn()
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('GuidedTour', () => {
  it('moves through steps and calls finish on the final step', () => {
    const onFinish = vi.fn()

    render(
      <>
        <button data-tour="first">First</button>
        <button data-tour="second">Second</button>
        <GuidedTour isOpen steps={steps} onFinish={onFinish} />
      </>,
    )

    expect(screen.getByRole('dialog')).toHaveTextContent('First control')

    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    expect(screen.getByRole('dialog')).toHaveTextContent('Second control')

    fireEvent.click(screen.getByRole('button', { name: /done/i }))
    expect(onFinish).toHaveBeenCalledTimes(1)
  })

  it('shows a fallback message when the target is not visible', () => {
    render(
      <GuidedTour
        isOpen
        steps={[
          {
            id: 'missing',
            selector: '[data-tour="missing"]',
            title: 'Missing control',
            body: 'This target is not present.',
          },
        ]}
        onFinish={vi.fn()}
      />,
    )

    expect(screen.getByRole('dialog')).toHaveTextContent('Missing control')
    expect(screen.getByText(/control is not visible yet/i)).toBeInTheDocument()
  })

  it('calls skip and finish callbacks when skipped', () => {
    const onFinish = vi.fn()
    const onSkip = vi.fn()

    render(<GuidedTour isOpen steps={steps} onFinish={onFinish} onSkip={onSkip} />)

    fireEvent.click(screen.getByRole('button', { name: /skip/i }))

    expect(onSkip).toHaveBeenCalledTimes(1)
    expect(onFinish).not.toHaveBeenCalled()
  })

  it('can be closed with Escape', () => {
    const onFinish = vi.fn()
    const onSkip = vi.fn()

    render(<GuidedTour isOpen steps={steps} onFinish={onFinish} onSkip={onSkip} />)

    fireEvent.keyDown(window, { key: 'Escape' })

    expect(onSkip).toHaveBeenCalledTimes(1)
    expect(onFinish).not.toHaveBeenCalled()
  })
})
