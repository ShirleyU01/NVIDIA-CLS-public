import { FormEvent, useMemo, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { isTeacherAuthed, setTeacherAuthed, validateTeacherCredentials } from '../auth/teacherAuth'
import { ROUTE_PATH } from '../routes/paths'

type LocationState = {
  from?: { pathname?: string; search?: string; hash?: string }
}

export function TeacherLoginPage() {
  const navigate = useNavigate()
  const location = useLocation()

  const fromPath = useMemo(() => {
    const state = (location.state ?? {}) as LocationState
    const from = state.from
    const pathname = from?.pathname ?? ROUTE_PATH.TEACHER_HOME
    const search = from?.search ?? ''
    const hash = from?.hash ?? ''
    return `${pathname}${search}${hash}`
  }, [location.state])

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')

    if (!validateTeacherCredentials(username.trim(), password)) {
      setTeacherAuthed(false)
      setError('Invalid username or password.')
      return
    }

    setTeacherAuthed(true)
    navigate(fromPath, { replace: true })
  }

  if (isTeacherAuthed()) {
    return <Navigate to={ROUTE_PATH.TEACHER_HOME} replace />
  }

  return (
    <main style={{ maxWidth: 440, margin: '40px auto', padding: '0 16px' }}>
      <h1 style={{ marginBottom: 8 }}>Teacher login</h1>
      <p style={{ marginTop: 0, opacity: 0.8 }}>Enter credentials to access teacher pages.</p>

      <form onSubmit={onSubmit} aria-label="Teacher login form">
        <label style={{ display: 'block', marginTop: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Username</div>
          <input
            name="username"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            style={{ width: '100%', padding: '10px 12px', fontSize: 16 }}
          />
        </label>

        <label style={{ display: 'block', marginTop: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Password</div>
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ width: '100%', padding: '10px 12px', fontSize: 16 }}
          />
        </label>

        {error ? (
          <div role="alert" style={{ marginTop: 12, color: '#b42318', fontWeight: 600 }}>
            {error}
          </div>
        ) : null}

        <button
          type="submit"
          style={{
            marginTop: 18,
            width: '100%',
            padding: '12px 14px',
            fontSize: 16,
            fontWeight: 700,
          }}
        >
          Log in
        </button>
      </form>
    </main>
  )
}

