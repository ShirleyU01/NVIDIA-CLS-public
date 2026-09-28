import { describe, expect, it } from 'vitest'

import { sanitizeStudentFeedbackMarkdown } from './sanitizeStudentFeedback'

describe('sanitizeStudentFeedbackMarkdown', () => {
  it('removes raw JSON before the student feedback heading', () => {
    const src = `{"summary":"hidden","correctness":"Correct","rubric":[]}

## Student feedback

Great job — well done.`
    const out = sanitizeStudentFeedbackMarkdown(src)
    expect(out).not.toContain('hidden')
    expect(out).toMatch(/^## Student feedback/)
    expect(out).toContain('Great job')
  })

  it('removes JSON between heading and prose', () => {
    const src = `## Student feedback

\`\`\`json
{"summary":"x","correctness":"Correct","rubric":[]}
\`\`\`

Excellent — this is correct.`
    const out = sanitizeStudentFeedbackMarkdown(src)
    expect(out).not.toContain('"summary"')
    expect(out).not.toContain('```')
    expect(out).toContain('Excellent')
  })
})
