import { useEffect, useRef, useState } from 'react'

import { StudyMathMarkdown } from './StudyMathMarkdown'
import styles from './StudyAmaDock.module.css'

export type AmaTurn = { role: string; content: string }

type Props = {
  sessionId: string | null
  turns: AmaTurn[]
  disabled: boolean
  onSend: (message: string) => Promise<void>
}

export function StudyAmaDock({ sessionId, turns, disabled, onSend }: Props) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const el = listRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [open, turns.length, sending])

  const handleSend = async () => {
    const msg = draft.trim()
    if (!msg || !sessionId) return
    setLocalError(null)
    setSending(true)
    try {
      await onSend(msg)
      setDraft('')
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : 'Could not send message.')
    } finally {
      setSending(false)
    }
  }

  const busy = disabled || sending

  return (
    <div className={styles.fab}>
      {open ? (
        <section className={styles.panel} aria-label="Ask me anything tutor chat">
          <header className={styles.panelHeader}>
            <div>
              <p className={styles.panelTitle}>Ask me anything</p>
              <p className={styles.panelHint}>
                Tutor stays on your practice problems and gives hints first. Ask explicitly if you want the
                full answer.
              </p>
            </div>
            <button type="button" className={styles.close} onClick={() => setOpen(false)} aria-label="Close chat">
              ×
            </button>
          </header>
          {localError ? (
            <p className={styles.error} role="alert">
              {localError}
            </p>
          ) : null}
          <div ref={listRef} className={styles.messages}>
            {turns.length === 0 ? (
              <p className={styles.empty}>
                Ask about the feedback or a step you are stuck on. The tutor will guide you with hints unless
                you ask for the complete solution.
              </p>
            ) : (
              turns.map((t, i) => {
                const isUser = t.role === 'user'
                return (
                  <div
                    key={`ama-turn-${i}`}
                    className={`${styles.bubble} ${isUser ? styles.bubbleUser : styles.bubbleTutor}`}
                  >
                    {isUser ? (
                      t.content
                    ) : (
                      <StudyMathMarkdown text={t.content} className={styles.tutorMath} />
                    )}
                  </div>
                )
              })
            )}
          </div>
          <div className={styles.composer}>
            <textarea
              className={styles.input}
              rows={2}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Message the tutor…"
              disabled={busy || !sessionId}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void handleSend()
                }
              }}
            />
            <button type="button" className={styles.send} onClick={() => void handleSend()} disabled={busy || !sessionId}>
              {sending ? '…' : 'Send'}
            </button>
          </div>
        </section>
      ) : null}
      <button
        type="button"
        className={styles.toggle}
        onClick={() => setOpen((v) => !v)}
        disabled={!sessionId}
        aria-expanded={open}
      >
        {open ? 'Hide tutor' : 'Ask me anything'}
      </button>
    </div>
  )
}
