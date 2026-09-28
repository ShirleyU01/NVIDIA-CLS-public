import { useMemo } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { ROUTE_PATH } from '../routes/paths'

export function StudentStudyPostSessionPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()

  const assessmentId = useMemo(() => {
    if (!sessionId) return ''
    try {
      return window.sessionStorage.getItem(`study:assessmentId:${sessionId}`) ?? ''
    } catch {
      return ''
    }
  }, [sessionId])

  const studentId = useMemo(() => {
    if (!sessionId) {
      try {
        return window.sessionStorage.getItem('study:studentId')?.trim() ?? ''
      } catch {
        return ''
      }
    }
    try {
      return (
        window.sessionStorage.getItem(`study:studentId:${sessionId}`)?.trim() ??
        window.sessionStorage.getItem('study:studentId')?.trim() ??
        ''
      )
    } catch {
      return ''
    }
  }, [sessionId])

  const startAnotherSession = () => {
    const next = new URLSearchParams()
    if (assessmentId) next.set('assessmentId', assessmentId)
    if (studentId) next.set('studentId', studentId)
    navigate(`${ROUTE_PATH.STUDENT_STUDY_CONFIG}${next.toString() ? `?${next.toString()}` : ''}`, {
      replace: true,
    })
  }

  const doneForDay = () => {
    if (!sessionId) {
      navigate(ROUTE_PATH.STUDENT_DONE, { replace: true })
      return
    }
    navigate(ROUTE_PATH.STUDENT_STUDY_SURVEY.replace(':sessionId', sessionId), { replace: true })
  }

  return (
    <main style={{ maxWidth: 720, margin: '40px auto', padding: '0 16px' }}>
      <h1 style={{ marginBottom: 8 }}>Done with this session</h1>
      <p style={{ marginTop: 0, opacity: 0.8 }}>
        Do you want to choose more practice problems, or are you done for the day?
      </p>

      <div style={{ display: 'grid', gap: 12, marginTop: 18 }}>
        <button
          type="button"
          onClick={startAnotherSession}
          style={{
            padding: '14px 16px',
            fontSize: 16,
            fontWeight: 800,
            borderRadius: 12,
            border: '1px solid #1b5e20',
            background: '#2e7d32',
            color: '#fff',
            cursor: 'pointer',
          }}
        >
          Choose more practice problems
        </button>
        <button
          type="button"
          onClick={doneForDay}
          style={{
            padding: '14px 16px',
            fontSize: 16,
            fontWeight: 800,
            borderRadius: 12,
            border: '1px solid #1b5e20',
            background: '#43a047',
            color: '#fff',
            cursor: 'pointer',
          }}
        >
          I’m done for the day
        </button>
      </div>
    </main>
  )
}

