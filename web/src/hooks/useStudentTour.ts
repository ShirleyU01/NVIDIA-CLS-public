import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'

import {
  getStudentTourRoute,
  isStudentRoute,
  STUDENT_TOUR_STORAGE_KEY,
  type StudentTourRouteKey,
} from '../tour/studentTourSteps'

type StoredStudentTourState = {
  completedRouteKeys: StudentTourRouteKey[]
}

const EMPTY_STORED_STATE: StoredStudentTourState = {
  completedRouteKeys: [],
}

function readStoredState(): StoredStudentTourState {
  try {
    const raw = window.localStorage.getItem(STUDENT_TOUR_STORAGE_KEY)
    if (!raw) return EMPTY_STORED_STATE
    const parsed = JSON.parse(raw) as Partial<StoredStudentTourState>
    return {
      completedRouteKeys: Array.isArray(parsed.completedRouteKeys)
        ? (parsed.completedRouteKeys as StudentTourRouteKey[])
        : [],
    }
  } catch {
    return EMPTY_STORED_STATE
  }
}

function writeStoredState(next: StoredStudentTourState) {
  try {
    window.localStorage.setItem(STUDENT_TOUR_STORAGE_KEY, JSON.stringify(next))
  } catch {
    // localStorage may be unavailable in private contexts; the guide still works for this page view.
  }
}

function markRouteComplete(routeKey: StudentTourRouteKey) {
  const stored = readStoredState()
  if (stored.completedRouteKeys.includes(routeKey)) return
  writeStoredState({
    completedRouteKeys: [...stored.completedRouteKeys, routeKey],
  })
}

export function useStudentTour() {
  const location = useLocation()
  const route = useMemo(() => getStudentTourRoute(location.pathname), [location.pathname])
  const [isOpen, setIsOpen] = useState(false)
  const [manualReplay, setManualReplay] = useState(false)
  const showStudentGuide = isStudentRoute(location.pathname)

  useEffect(() => {
    setManualReplay(false)
    if (!route || route.steps.length === 0) {
      setIsOpen(false)
      return
    }

    const stored = readStoredState()
    setIsOpen(!stored.completedRouteKeys.includes(route.key))
  }, [route])

  const finish = () => {
    if (route) markRouteComplete(route.key)
    setManualReplay(false)
    setIsOpen(false)
  }

  const start = () => {
    if (!route || route.steps.length === 0) return
    setManualReplay(true)
    setIsOpen(true)
  }

  return {
    isOpen,
    isManualReplay: manualReplay,
    showStudentGuide,
    steps: route?.steps ?? [],
    start,
    finish,
    skip: finish,
  }
}
