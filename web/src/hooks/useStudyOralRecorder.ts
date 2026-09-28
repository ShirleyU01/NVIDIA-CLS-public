import { useCallback, useRef, useState } from 'react'

function pickRecorderMimeType(): string | undefined {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/ogg;codecs=opus',
  ]
  for (const t of candidates) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(t)) {
      return t
    }
  }
  return undefined
}

export function useStudyOralRecorder() {
  const [recording, setRecording] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const stopTracks = useCallback(() => {
    if (streamRef.current) {
      for (const track of streamRef.current.getTracks()) track.stop()
    }
    streamRef.current = null
    mediaRecorderRef.current = null
  }, [])

  const startRecording = useCallback(async () => {
    setError(null)
    chunksRef.current = []
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const mimeType = pickRecorderMimeType()
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream)
      mediaRecorderRef.current = recorder
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      recorder.start(250)
      setRecording(true)
    } catch (e) {
      stopTracks()
      setRecording(false)
      setError(e instanceof Error ? e.message : 'Microphone access failed.')
      throw e
    }
  }, [stopTracks])

  const stopRecording = useCallback((): Promise<Blob> => {
    return new Promise((resolve, reject) => {
      const recorder = mediaRecorderRef.current
      if (!recorder || recorder.state === 'inactive') {
        stopTracks()
        setRecording(false)
        reject(new Error('No active recording.'))
        return
      }
      recorder.onstop = () => {
        const mime = recorder.mimeType || 'audio/webm'
        const blob = new Blob(chunksRef.current, { type: mime })
        chunksRef.current = []
        stopTracks()
        setRecording(false)
        if (blob.size === 0) {
          reject(new Error('Recording was empty. Try again and speak clearly.'))
          return
        }
        resolve(blob)
      }
      recorder.onerror = () => {
        stopTracks()
        setRecording(false)
        reject(new Error('Recording failed.'))
      }
      try {
        recorder.stop()
      } catch (e) {
        stopTracks()
        setRecording(false)
        reject(e instanceof Error ? e : new Error('Could not stop recording.'))
      }
    })
  }, [stopTracks])

  const cancelRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current
    if (recorder && recorder.state !== 'inactive') {
      try {
        recorder.stop()
      } catch {
        // ignore
      }
    }
    chunksRef.current = []
    stopTracks()
    setRecording(false)
  }, [stopTracks])

  return {
    recording,
    error,
    setError,
    startRecording,
    stopRecording,
    cancelRecording,
  }
}
