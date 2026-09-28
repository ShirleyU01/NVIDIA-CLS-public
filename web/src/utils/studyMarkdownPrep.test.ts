import { describe, expect, it } from 'vitest'

import { fixLatexForKatex, prepareStudyMarkdownForDisplay } from './studyMarkdownPrep'

describe('prepareStudyMarkdownForDisplay', () => {
  it('removes fenced json blocks', () => {
    const src = `## Hi

\`\`\`json
{"a": 1}
\`\`\`

Body here.`
    expect(prepareStudyMarkdownForDisplay(src)).not.toContain('```')
    expect(prepareStudyMarkdownForDisplay(src)).toContain('Body here.')
  })

  it('strips a leading JSON blob before markdown', () => {
    const src = `{"x":true}\n\n## Student feedback\n\nNice.`
    expect(prepareStudyMarkdownForDisplay(src)).toMatch(/^## Student feedback/)
  })

  it('converts paren delimiters and fixes malformed binom', () => {
    const src = String.raw`Use \(P(A \mid B)\) and \(\binom103\).`
    const out = fixLatexForKatex(src)
    expect(out).not.toContain(String.raw`\(`)
    expect(out).toContain('$P(A \\mid B)$')
    expect(out).toContain('\\binom{10}{3}')
  })

  it('fixes double backslash commands inside math spans', () => {
    const src = '$$P(3.5\\\\le X)=\\\\int_{3.5}^{6}\\\\frac{1}{6}\\\\,dx.$$'
    const out = fixLatexForKatex(src)
    expect(out).not.toContain('\\\\le')
    expect(out).not.toContain('\\\\int')
    expect(out).not.toContain('\\\\frac')
    expect(out).toContain('\\le')
    expect(out).toContain('\\int')
    expect(out).toContain('\\frac')
  })

  it('wraps bare subscripts in prose', () => {
    const src = 'Compare x_1 and x_{n}.'
    const out = fixLatexForKatex(src)
    expect(out).toContain('$x_1$')
    expect(out).toContain('$x_{n}$')
  })

  it('wraps bare superscripts in prose', () => {
    const src = 'Compare n^2 and n^{k}.'
    const out = fixLatexForKatex(src)
    expect(out).toContain('$n^2$')
    expect(out).toContain('$n^{k}$')
  })

  it('does not touch superscripts already inside math', () => {
    const src = 'See $n^2 + x^{k}$ above.'
    const out = fixLatexForKatex(src)
    expect(out).toBe('See $n^2 + x^{k}$ above.')
  })
})
