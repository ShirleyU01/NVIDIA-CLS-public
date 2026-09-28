const STORAGE_KEY = 'socrates.teacherAuth.v1'
const TEACHER_USERNAME = 'teacher'
const TEACHER_PASSWORD = 'dropouts210'

export function isTeacherAuthed(): boolean {
  return window.localStorage.getItem(STORAGE_KEY) === '1'
}

export function setTeacherAuthed(value: boolean): void {
  if (value) {
    window.localStorage.setItem(STORAGE_KEY, '1')
  } else {
    window.localStorage.removeItem(STORAGE_KEY)
  }
}

export function validateTeacherCredentials(username: string, password: string): boolean {
  return username === TEACHER_USERNAME && password === TEACHER_PASSWORD
}

export function getTeacherBasicAuthHeaderValue(): string {
  // Lightweight gate for demo environments only.
  return `Basic ${window.btoa(`${TEACHER_USERNAME}:${TEACHER_PASSWORD}`)}`
}

