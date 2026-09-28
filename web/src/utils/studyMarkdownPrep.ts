/**
 * Normalize LLM-authored study markdown before react-markdown + KaTeX.
 */

import { sanitizeStudentFeedbackMarkdown } from './sanitizeStudentFeedback'

const INLINE_PAREN_RE = /\\\((.+?)\\\)/gs
const DISPLAY_BRACKET_RE = /\\\[([\s\S]*?)\\\]/g
const BINOM_DIGITS_RE = /\\binom(?!\{)(\d+)/g
const FRAC_DIGITS_RE = /\\frac(?!\{)(\d{2,})/g
const BARE_SUBSCRIPT_RE = /(?<!\$)(?<![\\A-Za-z])([A-Za-z])_(\{[^}]+\}|\d+)/g
const BARE_SUPERSCRIPT_RE = /(?<!\$)(?<![\\A-Za-z\d])([A-Za-z\d])\^(\{[^}]+\}|\d+)/g
// Two backslashes before a command letter/punctuation inside math → one backslash.
// e.g. \\frac → \frac, \\le → \le, \\, → \,
const DOUBLE_BACKSLASH_CMD_RE = /\\\\([A-Za-z,;.!])/g
const MATH_SPAN_SPLIT_RE = /(\$\$[\s\S]*?\$\$|\$(?:[^$\\]|\\.)+\$)/g

function normalizeTimesOperator(s: string): string {
  // Common LLM phrasing: "6 times 2 = 12" → "6 × 2 = 12"
  // Limit to numeric tokens to avoid mangling normal prose ("many times").
  return s.replace(/(\d+)\s+times\s+(\d+)/gi, '$1 × $2')
}

function isEscaped(text: string, index: number): boolean {
  let backslashes = 0
  let pos = index - 1
  while (pos >= 0 && text[pos] === '\\') {
    backslashes++
    pos--
  }
  return backslashes % 2 === 1
}

function fixMathSpan(span: string): string {
  // Double backslash before command → single backslash (LLM sometimes emits \\frac instead of \frac)
  DOUBLE_BACKSLASH_CMD_RE.lastIndex = 0
  span = span.replace(DOUBLE_BACKSLASH_CMD_RE, '\\$1')
  // Malformed \binom / \frac without braces
  BINOM_DIGITS_RE.lastIndex = 0
  span = span.replace(BINOM_DIGITS_RE, (_, digits: string) => {
    if (digits.length < 2) return `\\binom${digits}`
    return `\\binom{${digits.slice(0, -1)}}{${digits.slice(-1)}}`
  })
  FRAC_DIGITS_RE.lastIndex = 0
  span = span.replace(FRAC_DIGITS_RE, (_, digits: string) => {
    if (digits.length < 2) return `\\frac${digits}`
    return `\\frac{${digits.slice(0, -1)}}{${digits.slice(-1)}}`
  })
  return span
}

function fixProse(prose: string): string {
  BARE_SUBSCRIPT_RE.lastIndex = 0
  BARE_SUPERSCRIPT_RE.lastIndex = 0
  // $$$1 = literal $ + capture group 1 (not $$ + literal 1)
  return prose.replace(BARE_SUBSCRIPT_RE, '$$$1_$2$').replace(BARE_SUPERSCRIPT_RE, '$$$1^$2$')
}

/** Convert ``\(...\)`` / ``\[...\]`` and repair common malformed commands for KaTeX. */
export function fixLatexForKatex(text: string): string {
  if (!text) return text
  let s = text.replace(/\r\n/g, '\n')
  s = s.replace(DISPLAY_BRACKET_RE, (_, body: string) => `$$${body.trim()}$$`)
  s = s.replace(INLINE_PAREN_RE, (_, body: string) => `$${body.trim()}$`)

  // Close unclosed single-$ spans
  let inMath = false
  let display = false
  let pos = 0
  while (pos < s.length) {
    if (s[pos] !== '$' || isEscaped(s, pos)) {
      pos++
      continue
    }
    const isDisplay = pos + 1 < s.length && s[pos + 1] === '$'
    const width = isDisplay ? 2 : 1
    if (!inMath) {
      inMath = true
      display = isDisplay
    } else if (isDisplay === display) {
      inMath = false
    }
    pos += width
  }
  if (inMath && !display) {
    s += '$'
  }

  // Fix math spans and prose separately
  MATH_SPAN_SPLIT_RE.lastIndex = 0
  const parts = s.split(MATH_SPAN_SPLIT_RE)
  s = parts.map((part, i) => (i % 2 === 1 ? fixMathSpan(part) : fixProse(part))).join('')

  return s
}

/** Strip leaked JSON fences / blobs; normalize math; trim. Safe to call on every render. */
export function prepareStudyMarkdownForDisplay(src: string): string {
  const t = sanitizeStudentFeedbackMarkdown(src ?? '')
  return normalizeTimesOperator(fixLatexForKatex(t)).trim()
}
