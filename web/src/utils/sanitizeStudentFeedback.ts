/**
 * Strip leaked grader JSON from student-visible study feedback markdown.
 * Defense in depth: Jetson sanitizes at write time; the UI sanitizes again at render.
 */

const JSON_FENCE_RE = /```\s*json\s*\r?\n([\s\S]*?)```/gi
const GENERIC_FENCE_RE = /```[^\n]*\r?\n([\s\S]*?)```/g
const STUDENT_FEEDBACK_HEADING_RE = /^##\s*Student\s+feedback\s*$/im

const JSON_SCHEMA_MARKERS = [
  '"correctness"',
  '"summary"',
  '"rubric"',
  '"key_mistakes"',
  '"next_steps"',
  '"clarifying_questions"',
]

function isJsonLikeBlob(blob: string): boolean {
  const st = blob.trim()
  if (!st) return false
  if (st.startsWith('{') || st.startsWith('[')) {
    try {
      JSON.parse(st)
      return true
    } catch {
      // continue
    }
  }
  const lowered = st.toLowerCase()
  return JSON_SCHEMA_MARKERS.some((m) => lowered.includes(m)) && st.includes('{')
}

function extractStudentFeedbackSection(text: string): string {
  const match = text.match(STUDENT_FEEDBACK_HEADING_RE)
  if (!match || match.index == null) return text
  return text.slice(match.index).trim()
}

function stripLeadingJsonObject(s: string): string {
  const st = s.trimStart()
  if (!st.startsWith('{')) return s
  let depth = 0
  let end = -1
  for (let i = 0; i < st.length; i++) {
    const ch = st[i]
    if (ch === '{') depth++
    else if (ch === '}') {
      depth--
      if (depth === 0) {
        end = i + 1
        break
      }
    }
  }
  if (end < 0) return s
  const blob = st.slice(0, end)
  const rest = st.slice(end).trimStart()
  if (!rest) return s
  try {
    JSON.parse(blob)
    return rest
  } catch {
    return s
  }
}

function stripLeadingJsonRuns(text: string): string {
  let t = text
  for (let i = 0; i < 8; i++) {
    const next = stripLeadingJsonObject(t)
    if (next === t) break
    t = next
  }
  return t
}

function stripJsonFences(text: string): string {
  let t = text
  for (let i = 0; i < 8; i++) {
    JSON_FENCE_RE.lastIndex = 0
    const withoutJsonFence = t.replace(JSON_FENCE_RE, '').trim()
    const withoutGeneric = withoutJsonFence.replace(GENERIC_FENCE_RE, (full, inner: string) =>
      isJsonLikeBlob(inner) ? '' : full,
    )
    if (withoutGeneric === t) break
    t = withoutGeneric.trim()
  }
  return t
}

function stripJsonAfterHeading(text: string): string {
  const match = text.match(STUDENT_FEEDBACK_HEADING_RE)
  if (!match || match.index == null) return text
  const heading = match[0]
  let body = text.slice(match.index + heading.length).replace(/^\n+/, '')
  body = stripJsonFences(body)
  body = stripLeadingJsonRuns(body)
  if (!body.trim()) return heading
  return `${heading}\n\n${body.trim()}`
}

export function sanitizeStudentFeedbackMarkdown(md: string): string {
  let text = (md ?? '').trim()
  if (!text) return text

  text = extractStudentFeedbackSection(text)
  text = stripJsonFences(text)
  text = stripLeadingJsonRuns(text)
  text = stripJsonAfterHeading(text)
  text = stripJsonFences(text)
  text = stripLeadingJsonRuns(text)
  return text.trim()
}
