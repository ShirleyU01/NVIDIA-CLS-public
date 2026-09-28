import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { isTeacherAuthed } from '../auth/teacherAuth'
import { ROUTE_PATH } from '../routes/paths'

export function RequireTeacherAuth() {
  const location = useLocation()

  if (!isTeacherAuthed()) {
    return <Navigate to={ROUTE_PATH.TEACHER_LOGIN} replace state={{ from: location }} />
  }

  return <Outlet />
}

