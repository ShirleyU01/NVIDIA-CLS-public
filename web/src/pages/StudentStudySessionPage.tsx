import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { studentStudyGuideApi } from '../api/studentStudyGuide'
import { StudyAmaDock } from '../components/StudyAmaDock'
import { StudyMathMarkdown } from '../components/StudyMathMarkdown'
import { useStudyOralRecorder } from '../hooks/useStudyOralRecorder'
import { ROUTE_PATH } from '../routes/paths'
import type { StudyAnswerMode, StudyRunState } from '../types/studyGuide'
import styles from './StudentStudySessionPage.module.css'

/** Encode the current video frame as JPEG — same pixels the student sees in the preview. */
async function snapshotVideoToJpeg(video: HTMLVideoElement, quality = 0.92): Promise<Blob> {
  const w = video.videoWidth
  const h = video.videoHeight
  if (!w || !h) {
    throw new Error('Camera preview is not ready yet — wait until you see the live video.')
  }
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Could not read image from camera preview.')
  ctx.drawImage(video, 0, 0, w, h)
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error('Could not encode image from camera.'))),
      'image/jpeg',
      quality,
    )
  })
}

export function StudentStudySessionPage() {
  const [state, setState] = useState<StudyRunState | null>(null)
  const [captureBusy, setCaptureBusy] = useState(false)
  const [gradeBusy, setGradeBusy] = useState(false)
  const [retakeBusy, setRetakeBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [endingStudy, setEndingStudy] = useState(false)
  const [nextBusy, setNextBusy] = useState(false)
  const [actionBusy] = useState(false)
  const [modeBusy, setModeBusy] = useState(false)
  const [oralBusy, setOralBusy] = useState(false)
  const oralRecorder = useStudyOralRecorder()
  const oralRecordStartedAtRef = useRef<number | null>(null)
  const [cameraEnabled, setCameraEnabled] = useState(false)
  const [cameraError, setCameraError] = useState<string | null>(null)
  const [stream, setStream] = useState<MediaStream | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const telemetryRef = useRef({
    pointerMoveCount: 0,
    pointerDistancePx: 0,
    lastPointerX: null as number | null,
    lastPointerY: null as number | null,
    scrollEventCount: 0,
    scrollDeltaYPx: 0,
    maxScrollYPx: 0,
    lastScrollYPx: 0,
  })

  const location = useLocation()
  const navigate = useNavigate()

  const sessionId = useMemo(() => {
    const params = new URLSearchParams(location.search)
    return params.get('sessionId')
  }, [location.search])

  const assessmentId = useMemo(() => {
    const params = new URLSearchParams(location.search)
    return params.get('assessmentId')
  }, [location.search])

  useEffect(() => {
    if (!sessionId) return

    const log = (type: string, data: Record<string, unknown> = {}, preferBeacon = false) => {
      void studentStudyGuideApi.logClientEvent(
        sessionId,
        {
          type,
          question_index: typeof state?.questionIndex === 'number' ? state.questionIndex - 1 : null,
          data,
        },
        { preferBeacon },
      )
    }

    const onVisibility = () => {
      log('page_visibility', { visibilityState: document.visibilityState, hidden: document.hidden })
    }

    const onPageHide = (e: PageTransitionEvent) => {
      log('page_unload', { event: 'pagehide', persisted: Boolean(e.persisted) }, true)
    }

    const onBeforeUnload = () => {
      log('page_unload', { event: 'beforeunload' }, true)
    }

    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('pagehide', onPageHide)
    window.addEventListener('beforeunload', onBeforeUnload)
    onVisibility()

    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('pagehide', onPageHide)
      window.removeEventListener('beforeunload', onBeforeUnload)
    }
  }, [sessionId, state?.questionIndex])

  useEffect(() => {
    if (!sessionId) return
    void studentStudyGuideApi.logClientEvent(sessionId, { type: 'study_session_page_viewed', data: {} })

    const flushEngagement = (preferBeacon = false) => {
      const t = telemetryRef.current
      const hasActivity = t.pointerMoveCount > 0 || t.scrollEventCount > 0
      if (!hasActivity) return
      void studentStudyGuideApi.logClientEvent(
        sessionId,
        {
          type: 'engagement_snapshot',
          question_index: typeof state?.questionIndex === 'number' ? state.questionIndex - 1 : null,
          data: {
            pointer_move_count: t.pointerMoveCount,
            pointer_distance_px: Math.round(t.pointerDistancePx),
            scroll_event_count: t.scrollEventCount,
            scroll_delta_y_px: Math.round(t.scrollDeltaYPx),
            max_scroll_y_px: Math.round(t.maxScrollYPx),
          },
        },
        { preferBeacon },
      )
      t.pointerMoveCount = 0
      t.pointerDistancePx = 0
      t.scrollEventCount = 0
      t.scrollDeltaYPx = 0
    }

    const onPointerMove = (event: PointerEvent) => {
      const t = telemetryRef.current
      t.pointerMoveCount += 1
      if (t.lastPointerX !== null && t.lastPointerY !== null) {
        const dx = event.clientX - t.lastPointerX
        const dy = event.clientY - t.lastPointerY
        t.pointerDistancePx += Math.sqrt(dx * dx + dy * dy)
      }
      t.lastPointerX = event.clientX
      t.lastPointerY = event.clientY
    }

    const onScroll = () => {
      const t = telemetryRef.current
      const y = window.scrollY
      t.scrollEventCount += 1
      t.scrollDeltaYPx += Math.abs(y - t.lastScrollYPx)
      t.lastScrollYPx = y
      t.maxScrollYPx = Math.max(t.maxScrollYPx, y)
    }

    const intervalId = window.setInterval(() => {
      flushEngagement(false)
    }, 10000)

    window.addEventListener('pointermove', onPointerMove, { passive: true })
    window.addEventListener('scroll', onScroll, { passive: true })

    return () => {
      window.clearInterval(intervalId)
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('scroll', onScroll)
      flushEngagement(true)
    }
  }, [sessionId, state?.questionIndex])

  useEffect(() => {
    if (!sessionId) return
    let cancelled = false
    const fetchState = async () => {
      try {
        const next = await studentStudyGuideApi.getState(sessionId)
        if (!cancelled) setState(next)
      } catch (err) {
        const status = (err as Error & { status?: number }).status
        // If Jetson backend restarted, its in-memory study runs are lost → 404.
        // Recover by re-creating the run using the existing central session id.
        if (status === 404) {
          const recoveredAssessmentId =
            assessmentId ?? window.sessionStorage.getItem(`study:assessmentId:${sessionId}`) ?? ''
          if (recoveredAssessmentId) {
            try {
              await studentStudyGuideApi.ensureRun(sessionId, recoveredAssessmentId)
              const next = await studentStudyGuideApi.getState(sessionId)
              if (!cancelled) setState(next)
              return
            } catch {
              // fall through to user-facing error below
            }
          }
        }
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load study state.')
        }
      }
    }
    void fetchState()
    const intervalId = window.setInterval(fetchState, 2500)
    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [sessionId, assessmentId])

  const stopCamera = () => {
    if (stream) {
      for (const track of stream.getTracks()) track.stop()
    }
    setStream(null)
    setCameraEnabled(false)
  }

  const startCamera = async () => {
    setCameraError(null)
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: 'environment',
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      })
      setStream(media)
      setCameraEnabled(true)
      if (sessionId) {
        void studentStudyGuideApi.logClientEvent(sessionId, { type: 'camera_started', data: {} })
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to enable camera.'
      setCameraError(msg)
      setCameraEnabled(false)
      if (sessionId) {
        void studentStudyGuideApi.logClientEvent(sessionId, { type: 'camera_error', data: { message: msg } })
      }
    }
  }

  useEffect(() => {
    const el = videoRef.current
    if (!el) return
    if (!stream) {
      el.srcObject = null
      return
    }
    el.srcObject = stream
    void el.play().catch(() => {
      // ignore autoplay block; user can click play via browser UI if needed
    })
  }, [stream])

  /** Short delay after stopping tracks so the kernel releases /dev/video* before the Jetson backend opens it. */
  const CAMERA_RELEASE_MS = 200

  const handleCapture = async () => {
    if (!sessionId) return
    setCaptureBusy(true)
    setError(null)
    const video = videoRef.current
    const canUseBrowserFrame = Boolean(
      stream && video && video.srcObject === stream && video.videoWidth > 0 && video.videoHeight > 0,
    )
    try {
      void studentStudyGuideApi.logClientEvent(sessionId, {
        type: 'capture_clicked',
        question_index: typeof state?.questionIndex === 'number' ? state.questionIndex - 1 : null,
        data: { mode: canUseBrowserFrame ? 'upload' : 'camera', captureCount: state?.captureCount ?? 0 },
      })
      if (canUseBrowserFrame && video) {
        // Same camera as /dev/video0: keep the browser stream open and send this frame to the server.
        // OpenCV on the Jetson cannot open the device while Firefox holds it.
        const blob = await snapshotVideoToJpeg(video)
        await studentStudyGuideApi.captureUpload(sessionId, blob)
        return
      }
      stopCamera()
      await new Promise<void>((resolve) => {
        window.setTimeout(resolve, CAMERA_RELEASE_MS)
      })
      await studentStudyGuideApi.capture(sessionId)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to capture.'
      setError(msg)
      void studentStudyGuideApi.logClientEvent(sessionId, {
        type: 'capture_client_error',
        question_index: typeof state?.questionIndex === 'number' ? state.questionIndex - 1 : null,
        data: { message: msg, mode: canUseBrowserFrame ? 'upload' : 'camera' },
      })
    } finally {
      setCaptureBusy(false)
      if (!canUseBrowserFrame) void startCamera()
    }
  }

  const handleGrade = async () => {
    if (!sessionId) return
    setGradeBusy(true)
    setError(null)
    try {
      void studentStudyGuideApi.logClientEvent(sessionId, {
        type: 'evaluation_clicked',
        question_index: typeof state?.questionIndex === 'number' ? state.questionIndex - 1 : null,
        data: { captureCount: state?.captureCount ?? 0 },
      })
      await studentStudyGuideApi.grade(sessionId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to grade captures.')
    } finally {
      setGradeBusy(false)
    }
  }

  const handleNextQuestion = async () => {
    if (!sessionId) return
    setNextBusy(true)
    setError(null)
    try {
      void studentStudyGuideApi.logClientEvent(sessionId, {
        type: 'next_question_clicked',
        question_index: typeof state?.questionIndex === 'number' ? state.questionIndex - 1 : null,
        data: { questionIndex: state?.questionIndex ?? null, questionCount: state?.questionCount ?? null },
      })
      const completedQuestionId =
        studentStudyGuideApi.getCurrentPracticeQuestionId(sessionId, state?.questionIndex ?? 1) ?? undefined
      await studentStudyGuideApi.nextQuestion(sessionId, completedQuestionId)
      const next = await studentStudyGuideApi.getState(sessionId)
      setState(next)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not go to next question.')
    } finally {
      setNextBusy(false)
    }
  }

  const handleAnswerModeChange = async (mode: StudyAnswerMode) => {
    if (!sessionId || mode === answerMode) return
    setModeBusy(true)
    setError(null)
    try {
      await studentStudyGuideApi.setAnswerMode(sessionId, mode)
      const next = await studentStudyGuideApi.getState(sessionId)
      setState(next)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not change answer mode.')
    } finally {
      setModeBusy(false)
    }
  }

  const handleOralStartRecording = async () => {
    if (!sessionId || oralRecorder.recording) return
    setError(null)
    oralRecorder.setError(null)
    try {
      void studentStudyGuideApi.logClientEvent(sessionId, {
        type: 'oral_record_started',
        question_index: typeof state?.questionIndex === 'number' ? state.questionIndex - 1 : null,
        data: {},
      })
      oralRecordStartedAtRef.current = Date.now()
      await oralRecorder.startRecording()
    } catch {
      // error set on hook
    }
  }

  const handleOralDoneSpeaking = async () => {
    if (!sessionId || !oralRecorder.recording) return
    setOralBusy(true)
    setError(null)
    try {
      const recordDurationMs =
        oralRecordStartedAtRef.current != null
          ? Math.max(0, Date.now() - oralRecordStartedAtRef.current)
          : null
      const blob = await oralRecorder.stopRecording()
      oralRecordStartedAtRef.current = null
      void studentStudyGuideApi.logClientEvent(sessionId, {
        type: 'oral_record_stopped',
        question_index: typeof state?.questionIndex === 'number' ? state.questionIndex - 1 : null,
        data: {
          bytes: blob.size,
          record_duration_ms: recordDurationMs,
        },
      })
      await studentStudyGuideApi.uploadOralAnswer(sessionId, blob)
      const next = await studentStudyGuideApi.getState(sessionId)
      setState(next)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload recording.')
    } finally {
      setOralBusy(false)
    }
  }

  const handleRetakeOral = async () => {
    if (!sessionId) return
    setOralBusy(true)
    setError(null)
    try {
      await studentStudyGuideApi.retakeOral(sessionId)
      const next = await studentStudyGuideApi.getState(sessionId)
      setState(next)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not clear recording.')
    } finally {
      setOralBusy(false)
    }
  }

  const handleAmaSend = async (message: string) => {
    if (!sessionId) return
    setError(null)
    void studentStudyGuideApi.logClientEvent(sessionId, {
      type: 'ama_send_clicked',
      question_index: typeof state?.questionIndex === 'number' ? state.questionIndex - 1 : null,
      data: { message_length: message.length },
    })
    await studentStudyGuideApi.actionAma(sessionId, message)
    const next = await studentStudyGuideApi.getState(sessionId)
    setState(next)
  }

  const status = state?.status ?? 'idle'
  const hasFeedback = Boolean(state?.feedbackMarkdown?.trim())
  const qIdx = state?.questionIndex ?? 1
  const qCount = state?.questionCount ?? 1
  const captureCount = state?.captureCount ?? 0
  const captureLimit = state?.captureLimit ?? 5
  const canCaptureMore = captureCount < captureLimit
  const answerMode: StudyAnswerMode = state?.answerMode ?? 'paper'
  const isOralMode = answerMode === 'oral'
  const canGrade = isOralMode ? Boolean(state?.oralHasRecording) : captureCount > 0
  const canGoNext = hasFeedback && qCount > 1 && qIdx < qCount
  const hints = state?.hints?.filter((hint) => hint.trim()) ?? []
  const isBusy =
    retakeBusy ||
    captureBusy ||
    gradeBusy ||
    nextBusy ||
    actionBusy ||
    modeBusy ||
    oralBusy ||
    status === 'capturing' ||
    status === 'thinking'
  const isOralRecording = oralRecorder.recording
  const isOralTranscribing = oralBusy || (status === 'thinking' && isOralMode && !state?.oralHasRecording)
  const canChangeAnswerMode =
    !hasFeedback &&
    captureCount === 0 &&
    !state?.oralHasRecording &&
    !isBusy &&
    !isOralRecording
  const latestImageSrc =
    state?.latestImageUrl?.trim() && sessionId ? `${import.meta.env.VITE_JETSON_API_BASE_URL ?? 'http://localhost:8001'}${state.latestImageUrl}` : ''

  useEffect(() => {
    if (isOralMode) {
      stopCamera()
      return
    }
    void startCamera()
    return () => stopCamera()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOralMode, sessionId, state?.questionIndex])

  const handleRetakeLast = async () => {
    if (!sessionId) return
    setRetakeBusy(true)
    setError(null)
    try {
      void studentStudyGuideApi.logClientEvent(sessionId, {
        type: 'retake_clicked',
        question_index: typeof state?.questionIndex === 'number' ? state.questionIndex - 1 : null,
        data: { captureCount: state?.captureCount ?? 0 },
      })
      await studentStudyGuideApi.retakeLast(sessionId)
      const next = await studentStudyGuideApi.getState(sessionId)
      setState(next)
      if (!cameraEnabled) void startCamera()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retake photo.')
    } finally {
      setRetakeBusy(false)
    }
  }

  return (
    <main className={styles.page}>
      <section className={styles.left}>
        <section
          className={`${styles.panel} ${styles.question}`}
          aria-label="Study Question"
          data-tour="student-study-question"
        >
          <header className={styles.headerRow}>
            <p className={styles.kicker}>
              {sessionId ? `Session ${sessionId}` : 'Connecting'}
              {qCount > 1 ? ` · Question ${qIdx} of ${qCount}` : null}
            </p>
            <p className={styles.statusPill} data-tour="student-study-status">
              {status === 'idle'
                ? 'Ready'
                : status === 'capturing'
                  ? 'Capturing…'
                  : status === 'thinking'
                    ? isOralMode && !hasFeedback && state?.oralHasRecording
                      ? 'Transcribing…'
                      : 'Evaluating…'
                    : status === 'done'
                      ? 'Feedback ready'
                      : 'Error'}
            </p>
          </header>

          <div className={styles.modeRow} role="group" aria-label="How to submit your answer">
            <p className={styles.modeLabel}>Submit your answer by:</p>
            <div className={styles.modeToggle}>
              <button
                type="button"
                className={`${styles.modeButton} ${!isOralMode ? styles.modeButtonActive : ''}`}
                onClick={() => void handleAnswerModeChange('paper')}
                disabled={!canChangeAnswerMode || !isOralMode}
                aria-pressed={!isOralMode}
              >
                Write on paper
              </button>
              <button
                type="button"
                className={`${styles.modeButton} ${isOralMode ? styles.modeButtonActive : ''}`}
                onClick={() => void handleAnswerModeChange('oral')}
                disabled={!canChangeAnswerMode || isOralMode}
                aria-pressed={isOralMode}
              >
                Speak (microphone)
              </button>
            </div>
          </div>

          <div className={styles.questionBody}>
            {state?.questionText?.trim() ? (
              <StudyMathMarkdown text={state.questionText} />
            ) : (
              <p>Waiting for the proctor service to provide the question...</p>
            )}
          </div>

          {hints.length > 0 ? (
            <section className={styles.hintsPanel} aria-label="Question hints">
              <div className={styles.hintsHeader}>
                <p className={styles.hintsTitle}>Stuck? Open a hint when you need one.</p>
              </div>
              <div className={styles.hintFolders}>
                {hints.map((hint, index) => (
                  <details key={`${index}-${hint}`} className={styles.hintFolder}>
                    <summary className={styles.hintSummary}>
                      <span className={styles.hintChevron} aria-hidden>
                        ▸
                      </span>
                      <span className={styles.hintFolderTab} aria-hidden />
                      <span>Hint {index + 1}</span>
                      <span className={styles.hintMeta}>
                        {index === 0 ? 'gentle nudge' : index === 1 ? 'more direction' : 'strongest hint'}
                      </span>
                    </summary>
                    <StudyMathMarkdown text={hint} className={styles.hintText} />
                  </details>
                ))}
              </div>
            </section>
          ) : null}

          <div className={styles.instructions}>
            <p className={styles.instructionsTitle}>What to do</p>
            {isOralMode ? (
              <ol className={styles.instructionsList}>
                <li>
                  You chose to <strong>speak</strong> your answer. Prefer paper? Use <strong>Write on paper</strong>{' '}
                  above (before you record).
                </li>
                <li>Work through the problem out loud — explain your reasoning step by step.</li>
                <li>Tap Record, speak your answer, then tap I&apos;m done speaking when you finish.</li>
                <li>Review the transcript, then evaluate when you are ready.</li>
                <li>Use Ask me anything for hints (text replies only).</li>
              </ol>
            ) : (
              <ol className={styles.instructionsList}>
                <li>
                  You chose to <strong>write on paper</strong>. Prefer to talk through it? Use{' '}
                  <strong>Speak (microphone)</strong> above instead.
                </li>
                <li>Solve the problem on paper.</li>
                <li>Use the preview to frame your page roughly inside the guide (doesn’t need to be perfect).</li>
                <li>Capture each page (up to {captureLimit}) using the preview.</li>
                <li>When you’re done, click “I’m done — evaluate my pages”.</li>
              </ol>
            )}
          </div>

          {isOralMode ? (
            <section className={styles.oralPanel} aria-label="Spoken answer">
              {oralRecorder.error ? (
                <p className={styles.error} role="alert">
                  {oralRecorder.error}
                </p>
              ) : null}
              <p className={styles.oralHint}>
                Speak your solution clearly — you can also switch to Write on paper above before you start. The tutor
                sees your transcript in Ask me anything and when you evaluate.
              </p>
              {isOralRecording ? (
                <div className={styles.recordingBanner} role="status" aria-live="polite">
                  <span className={styles.recordingDot} aria-hidden />
                  <span>Recording — explain your work out loud</span>
                </div>
              ) : null}
              <div className={styles.oralActions}>
                {isOralRecording ? (
                  <button
                    type="button"
                    className={styles.doneSpeakingButton}
                    onClick={() => void handleOralDoneSpeaking()}
                    disabled={!sessionId || oralBusy}
                  >
                    {oralBusy ? 'Saving…' : "I'm done speaking"}
                  </button>
                ) : (
                  <button
                    type="button"
                    className={styles.captureButton}
                    onClick={() => void handleOralStartRecording()}
                    disabled={!sessionId || isBusy || isOralTranscribing}
                  >
                    {isOralTranscribing
                      ? 'Transcribing…'
                      : state?.oralHasRecording
                        ? 'Record again'
                        : 'Record answer'}
                  </button>
                )}
                {state?.oralHasRecording && !isOralRecording ? (
                  <button
                    type="button"
                    className={styles.previewButton}
                    onClick={() => void handleRetakeOral()}
                    disabled={!sessionId || isBusy || oralBusy}
                  >
                    Clear recording
                  </button>
                ) : null}
                {!isOralRecording ? (
                  <button
                    type="button"
                    className={styles.captureButton}
                    onClick={handleGrade}
                    disabled={!sessionId || isBusy || oralBusy || !canGrade}
                  >
                    {gradeBusy || (status === 'thinking' && state?.oralHasRecording)
                      ? 'Evaluating…'
                      : 'Evaluate my spoken answer'}
                  </button>
                ) : null}
              </div>
              {state?.oralTranscript?.trim() ? (
                <div className={styles.transcriptBox} aria-label="Transcript of your recording">
                  <p className={styles.transcriptLabel}>Your transcript</p>
                  <p className={styles.transcriptText}>{state.oralTranscript}</p>
                </div>
              ) : null}
            </section>
          ) : (
          <>
          <section className={styles.previewPanel} aria-label="Camera preview">
            <header className={styles.previewHeader}>
              <p className={styles.previewTitle}>Preview</p>
              <div className={styles.previewControls}>
                {cameraEnabled ? (
                  <button
                    type="button"
                    className={styles.previewButton}
                    data-tour="student-study-preview-toggle"
                    onClick={stopCamera}
                    disabled={isBusy}
                  >
                    Stop preview
                  </button>
                ) : (
                  <button
                    type="button"
                    className={styles.previewButton}
                    data-tour="student-study-preview-toggle"
                    onClick={startCamera}
                    disabled={isBusy}
                  >
                    Enable preview
                  </button>
                )}
              </div>
            </header>
            {cameraError ? <p className={styles.error} role="alert">{cameraError}</p> : null}
            <div className={styles.videoWrap}>
              <video ref={videoRef} className={styles.video} playsInline muted />
              <div className={styles.a4Guide} aria-hidden />
            </div>
            <p className={styles.previewHint}>
              Tip: keep the page flat, avoid glare, and make sure the writing is sharp and readable.
            </p>
          </section>

          <div style={{ display: 'grid', gap: 10 }}>
            <button
              type="button"
              className={styles.captureButton}
              data-tour="student-capture-grade"
              onClick={handleCapture}
              disabled={!sessionId || isBusy || !canCaptureMore}
            >
              {captureBusy || status === 'capturing'
                ? 'Capturing…'
                : canCaptureMore
                  ? `Capture page (${captureCount}/${captureLimit})`
                  : `Capture limit reached (${captureLimit})`}
            </button>
            <button
              type="button"
              className={styles.captureButton}
              onClick={handleGrade}
              disabled={!sessionId || isBusy || !canGrade}
            >
              {gradeBusy || status === 'thinking' ? 'Evaluating…' : 'I’m done — evaluate my pages'}
            </button>
          </div>

          {latestImageSrc ? (
            <figure className={styles.imageFigure} aria-label="Captured photo preview">
              <img className={styles.capturedImage} src={latestImageSrc} alt="Captured photo preview" />
              <figcaption className={styles.imageCaption}>
                Last captured photo preview ({captureCount}/{captureLimit})
              </figcaption>
              <div style={{ display: 'flex', gap: 10, justifyContent: 'center', marginTop: 10 }}>
                <button
                  type="button"
                  className={styles.previewButton}
                  onClick={handleRetakeLast}
                  disabled={!sessionId || isBusy}
                >
                  {retakeBusy ? 'Retaking…' : 'Retake last photo'}
                </button>
              </div>
            </figure>
          ) : null}
          </>
          )}
        </section>

        <section
          className={`${styles.panel} ${styles.feedback}`}
          aria-label="Feedback"
          data-tour="student-study-feedback"
        >
          {state?.error ? <p className={styles.error} role="alert">{state.error}</p> : null}
          {error ? <p className={styles.error} role="alert">{error}</p> : null}

          {hasFeedback ? (
            <>
              <h2 className={styles.sectionTitle}>Feedback</h2>
              <div className={styles.markdown} aria-label="Feedback">
                <StudyMathMarkdown text={state?.feedbackMarkdown ?? ''} />
              </div>

              <p style={{ margin: '10px 0 0', fontWeight: 700 }}>
                Need help? Click{' '}
                <span style={{ color: '#b42318', fontWeight: 900 }}>Ask me anything</span> (bottom-right).
              </p>

              <div className={styles.ctaRow} aria-label="Next steps after feedback">
                {canGoNext ? (
                  <button
                    type="button"
                    className={styles.ctaButton}
                    onClick={handleNextQuestion}
                    disabled={isBusy}
                  >
                    Next question
                  </button>
                ) : null}
              </div>
            </>
          ) : (
            <p className={styles.placeholder}>
              {isOralMode
                ? 'After you record and evaluate your spoken answer, feedback will appear here.'
                : 'After you capture your paper, feedback will appear here.'}
            </p>
          )}
        </section>

        <button
          type="button"
          className={styles.doneLink}
          data-tour="student-end-study"
          onClick={async () => {
            if (!sessionId) {
              navigate(ROUTE_PATH.STUDENT_DONE)
              return
            }
            setEndingStudy(true)
            setError(null)
            try {
              void studentStudyGuideApi.logClientEvent(sessionId, {
                type: 'end_study_clicked',
                question_index: typeof state?.questionIndex === 'number' ? state.questionIndex - 1 : null,
                data: { questionIndex: state?.questionIndex ?? null, questionCount: state?.questionCount ?? null },
              })
              // Triggers Jetson aggregation + LLM build + central upload.
              // We always navigate to the review page even if this fails so
              // the student isn't trapped here; the review page polls and
              // surfaces a "no feedback available" state if nothing arrives.
              const completedQuestionId = hasFeedback
                ? studentStudyGuideApi.getCurrentPracticeQuestionId(sessionId, state?.questionIndex ?? 1) ??
                  undefined
                : undefined
              await studentStudyGuideApi.endRun(sessionId, completedQuestionId)
            } catch (err) {
              setError(err instanceof Error ? err.message : 'Failed to end study run.')
            } finally {
              setEndingStudy(false)
              const reviewPath = ROUTE_PATH.STUDENT_STUDY_REVIEW.replace(
                ':sessionId',
                encodeURIComponent(sessionId),
              )
              navigate(reviewPath)
            }
          }}
          disabled={endingStudy || isBusy}
        >
          {endingStudy ? 'Ending study…' : 'End Study'}
        </button>
      </section>

      <StudyAmaDock
        sessionId={sessionId}
        turns={state?.amaTurns ?? []}
        disabled={isBusy || isOralRecording}
        onSend={handleAmaSend}
      />
    </main>
  )
}

