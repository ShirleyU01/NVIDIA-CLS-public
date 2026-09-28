import ReactMarkdown from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkMath from 'remark-math'

import 'katex/dist/katex.min.css'

import styles from './StudyMathMarkdown.module.css'
import { prepareStudyMarkdownForDisplay } from '../utils/studyMarkdownPrep'

type Props = {
  text: string
  className?: string
}

/**
 * Renders study feedback as Markdown with LaTeX ($...$, $$...$$) via KaTeX.
 */
export function StudyMathMarkdown({ text, className }: Props) {
  const merged = [styles.root, className].filter(Boolean).join(' ')
  const body = prepareStudyMarkdownForDisplay(text)
  return (
    <div className={merged}>
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false, trust: false }]]}
      >
        {body}
      </ReactMarkdown>
    </div>
  )
}
