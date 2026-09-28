import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'

import styles from './GuidedTour.module.css'

export type GuidedTourStep = {
  id: string
  selector: string
  title: string
  body: string
  placement?: 'top' | 'right' | 'bottom' | 'left'
}

type GuidedTourProps = {
  isOpen: boolean
  steps: GuidedTourStep[]
  onFinish: () => void
  onSkip?: () => void
}

type TooltipPosition = {
  top: number
  left: number
  placement: NonNullable<GuidedTourStep['placement']>
}

type TooltipSize = {
  width: number
  height: number
}

const TOOLTIP_WIDTH = 320
const TOOLTIP_GAP = 14
const VIEWPORT_MARGIN = 16
const DEFAULT_TOOLTIP_SIZE: TooltipSize = {
  width: TOOLTIP_WIDTH,
  height: 220,
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
}

function getTargetElement(selector: string): HTMLElement | null {
  try {
    return document.querySelector<HTMLElement>(selector)
  } catch {
    return null
  }
}

function getTooltipPosition(
  rect: DOMRect,
  preferredPlacement: NonNullable<GuidedTourStep['placement']>,
  tooltipSize: TooltipSize,
): TooltipPosition {
  const viewportWidth = window.innerWidth
  const viewportHeight = window.innerHeight
  const tooltipWidth = Math.min(tooltipSize.width || TOOLTIP_WIDTH, viewportWidth - VIEWPORT_MARGIN * 2)
  const tooltipHeight = tooltipSize.height || DEFAULT_TOOLTIP_SIZE.height
  const maxLeft = Math.max(VIEWPORT_MARGIN, viewportWidth - tooltipWidth - VIEWPORT_MARGIN)
  const maxTop = Math.max(VIEWPORT_MARGIN, viewportHeight - tooltipHeight - VIEWPORT_MARGIN)
  const centeredLeft = rect.left + rect.width / 2 - tooltipWidth / 2
  const centeredTop = rect.top + rect.height / 2 - tooltipHeight / 2
  const dockedRight = {
    top: clamp(centeredTop, VIEWPORT_MARGIN, maxTop),
    left: maxLeft,
    placement: 'right' as const,
  }

  const hasRoomBelow = rect.bottom + TOOLTIP_GAP + tooltipHeight <= viewportHeight - VIEWPORT_MARGIN
  const hasRoomAbove = rect.top - TOOLTIP_GAP - tooltipHeight >= VIEWPORT_MARGIN

  if (preferredPlacement === 'top') {
    if (!hasRoomAbove) return dockedRight
    return {
      top: clamp(rect.top - tooltipHeight - TOOLTIP_GAP, VIEWPORT_MARGIN, maxTop),
      left: clamp(centeredLeft, VIEWPORT_MARGIN, maxLeft),
      placement: preferredPlacement,
    }
  }

  if (preferredPlacement === 'left') {
    return {
      top: clamp(centeredTop, VIEWPORT_MARGIN, maxTop),
      left: clamp(rect.left - tooltipWidth - TOOLTIP_GAP, VIEWPORT_MARGIN, maxLeft),
      placement: preferredPlacement,
    }
  }

  if (preferredPlacement === 'right') {
    return {
      top: clamp(centeredTop, VIEWPORT_MARGIN, maxTop),
      left: clamp(rect.right + TOOLTIP_GAP, VIEWPORT_MARGIN, maxLeft),
      placement: preferredPlacement,
    }
  }

  if (!hasRoomBelow) return dockedRight

  return {
    top: clamp(rect.bottom + TOOLTIP_GAP, VIEWPORT_MARGIN, maxTop),
    left: clamp(centeredLeft, VIEWPORT_MARGIN, maxLeft),
    placement: preferredPlacement,
  }
}

export function GuidedTour({ isOpen, steps, onFinish, onSkip }: GuidedTourProps) {
  const [activeIndex, setActiveIndex] = useState(0)
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null)
  const [tooltipSize, setTooltipSize] = useState<TooltipSize>(DEFAULT_TOOLTIP_SIZE)
  const closeButtonRef = useRef<HTMLButtonElement | null>(null)
  const tooltipRef = useRef<HTMLElement | null>(null)
  const pendingTargetRectTimeout = useRef<number | null>(null)
  const step = steps[activeIndex] ?? null

  const updateTarget = useCallback(
    () => {
      if (!step) {
        setTargetRect(null)
        return
      }

      const target = getTargetElement(step.selector)
      if (!target) {
        setTargetRect(null)
        return
      }

      target.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' })
      if (pendingTargetRectTimeout.current != null) {
        window.clearTimeout(pendingTargetRectTimeout.current)
      }
      pendingTargetRectTimeout.current = window.setTimeout(() => {
        setTargetRect(target.getBoundingClientRect())
      }, 120)
    },
    [step],
  )

  useEffect(() => {
    return () => {
      if (pendingTargetRectTimeout.current != null) {
        window.clearTimeout(pendingTargetRectTimeout.current)
        pendingTargetRectTimeout.current = null
      }
    }
  }, [])

  useEffect(() => {
    if (!isOpen) return
    setActiveIndex(0)
  }, [isOpen, steps])

  useLayoutEffect(() => {
    if (!isOpen) return
    updateTarget()
  }, [isOpen, updateTarget])

  useLayoutEffect(() => {
    if (!isOpen || !tooltipRef.current) return

    const updateTooltipSize = () => {
      if (!tooltipRef.current) return
      const rect = tooltipRef.current.getBoundingClientRect()
      setTooltipSize({
        width: rect.width || DEFAULT_TOOLTIP_SIZE.width,
        height: rect.height || DEFAULT_TOOLTIP_SIZE.height,
      })
    }

    updateTooltipSize()

    if (typeof ResizeObserver === 'undefined') return

    const observer = new ResizeObserver(updateTooltipSize)
    observer.observe(tooltipRef.current)
    return () => observer.disconnect()
  }, [isOpen, step])

  useEffect(() => {
    if (!isOpen) return
    closeButtonRef.current?.focus()

    const closeAsSkipped = () => {
      if (onSkip) {
        onSkip()
      } else {
        onFinish()
      }
    }

    const handlePositionChange = () => updateTarget()
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closeAsSkipped()
      } else if (event.key === 'ArrowRight' || event.key === 'Enter') {
        setActiveIndex((current) => {
          if (current >= steps.length - 1) {
            onFinish()
            return current
          }
          return current + 1
        })
      } else if (event.key === 'ArrowLeft') {
        setActiveIndex((current) => Math.max(0, current - 1))
      }
    }

    window.addEventListener('resize', handlePositionChange)
    window.addEventListener('scroll', handlePositionChange, true)
    window.addEventListener('keydown', handleKeyDown)

    return () => {
      window.removeEventListener('resize', handlePositionChange)
      window.removeEventListener('scroll', handlePositionChange, true)
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen, onFinish, onSkip, steps.length, updateTarget])

  if (!isOpen || !step || steps.length === 0) return null

  const currentStep = activeIndex + 1
  const isLastStep = activeIndex === steps.length - 1
  const tooltipPosition = targetRect
    ? getTooltipPosition(targetRect, step.placement ?? 'bottom', tooltipSize)
    : null

  const handleNext = () => {
    if (isLastStep) {
      onFinish()
      return
    }
    setActiveIndex((current) => current + 1)
  }

  const handleSkip = () => {
    if (onSkip) {
      onSkip()
    } else {
      onFinish()
    }
  }

  return (
    <div className={styles.root} aria-live="polite">
      <div className={styles.scrim} />
      {targetRect ? (
        <div
          className={styles.spotlight}
          style={{
            top: targetRect.top - 8,
            left: targetRect.left - 8,
            width: targetRect.width + 16,
            height: targetRect.height + 16,
          }}
          aria-hidden
        />
      ) : null}
      <section
        ref={tooltipRef}
        className={`${styles.tooltip} ${!tooltipPosition ? styles.tooltipCentered : ''}`}
        style={
          tooltipPosition
            ? {
                top: tooltipPosition.top,
                left: tooltipPosition.left,
              }
            : undefined
        }
        role="dialog"
        aria-modal="true"
        aria-labelledby="guided-tour-title"
        aria-describedby="guided-tour-body"
        data-placement={tooltipPosition?.placement ?? 'center'}
      >
        <p className={styles.stepCount}>
          Step {currentStep} of {steps.length}
        </p>
        <h2 className={styles.title} id="guided-tour-title">
          {step.title}
        </h2>
        <p className={styles.body} id="guided-tour-body">
          {step.body}
        </p>
        {!targetRect ? (
          <p className={styles.fallbackHint}>
            This control is not visible yet. Continue when it appears, or skip this guide.
          </p>
        ) : null}
        <div className={styles.actions}>
          <button ref={closeButtonRef} type="button" className={styles.secondaryButton} onClick={handleSkip}>
            Skip
          </button>
          <button
            type="button"
            className={styles.secondaryButton}
            onClick={() => setActiveIndex((current) => Math.max(0, current - 1))}
            disabled={activeIndex === 0}
          >
            Back
          </button>
          <button type="button" className={styles.primaryButton} onClick={handleNext}>
            {isLastStep ? 'Done' : 'Next'}
          </button>
        </div>
      </section>
    </div>
  )
}
