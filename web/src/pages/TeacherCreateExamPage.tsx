import { useState } from 'react'

import { teacherApi } from '../api/teacher'
import styles from './TeacherCreateExamPage.module.css'

type RubricCriterionForm = {
  id: string
  name: string
  max: number
}

export function TeacherCreateExamPage() {
  const [title, setTitle] = useState("Bayes' Rule Oral Exam")
  const [questionsText, setQuestionsText] = useState('What is Bayes rule?\nGive an example.')
  const [lectureMaterial, setLectureMaterial] = useState(
    'Optional: Paste lecture notes or source material here. The AI will use this to ask follow-up questions and to grade answers.'
  )
  const [criteria, setCriteria] = useState<RubricCriterionForm[]>([
    { id: 'C1', name: 'States correct formula', max: 2 },
    { id: 'C2', name: 'Explains each term', max: 2 },
  ])

  const questions = questionsText
    .split('\n')
    .map((q) => q.trim())
    .filter(Boolean)

  const rubricJson = {
    rubric_id: 'demo_rubric_v1',
    scale: { min: 0, max: 2 },
    criteria: criteria.map((c) => ({
      id: c.id,
      name: c.name,
      description: c.name,
      max: c.max,
      weight: 1.0,
      anchors: {
        '0': 'Missing or incorrect.',
        '1': 'Partially correct.',
        '2': 'Fully correct.',
      },
    })),
  }

  const examConfigJson = {
    exam_id: 'demo_exam_v1',
    title,
    system_prompt: 'You are an oral exam proctor.',
    lecture_material: lectureMaterial.trim() || undefined,
    post_exam_follow_ups: 1,
    questions: questions.map((q, index) => ({
      id: `Q${index + 1}`,
      text: q,
      rubric_items: criteria.map((c) => c.name),
    })),
  }

  const [submitStatus, setSubmitStatus] = useState<string | null>(null)

  const handleSubmitToBackend = async () => {
    setSubmitStatus('Submitting...')
    try {
      const { assessmentId } = await teacherApi.createAssessment({
        title,
        rubricJson,
        questionSetJson: examConfigJson,
      })
      if (assessmentId != null) {
        setSubmitStatus(`Created assessment with id ${assessmentId}.`)
      } else {
        setSubmitStatus('Backend not configured; JSON generated locally only.')
      }
    } catch (err) {
      setSubmitStatus(
        err instanceof Error ? `Error creating assessment: ${err.message}` : 'Error creating assessment.',
      )
    }
  }

  const handleAddCriterion = () => {
    setCriteria((prev) => [
      ...prev,
      { id: `C${prev.length + 1}`, name: `Criterion ${prev.length + 1}`, max: 2 },
    ])
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Create New Exam</h1>
        <p className={styles.subtitle}>
          Fill out this form to generate rubric and exam JSON that you can plug into the backend.
        </p>
      </header>

      <section className={styles.formGrid}>
        <section className={styles.card}>
          <h2>Assessment Basics</h2>
          <label className={styles.field}>
            <span>Assessment Title</span>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Bayes' Rule Oral Exam"
            />
          </label>

          <label className={styles.field}>
            <span>Questions (One Per Line)</span>
            <textarea
              rows={5}
              value={questionsText}
              onChange={(e) => setQuestionsText(e.target.value)}
            />
          </label>

          <label className={styles.field}>
            <span>Lecture / Source Material (optional)</span>
            <textarea
              rows={8}
              value={lectureMaterial}
              onChange={(e) => setLectureMaterial(e.target.value)}
              placeholder="Paste notes, slides, or textbook excerpts. The AI will use this to ask follow-ups and grade answers."
            />
          </label>
        </section>

        <section className={styles.card}>
          <h2>Rubric Criteria</h2>
          <div className={styles.criteriaList}>
            {criteria.map((c, index) => (
              <div className={styles.criterionRow} key={c.id}>
                <input
                  className={styles.criterionId}
                  type="text"
                  value={c.id}
                  onChange={(e) => {
                    const next = [...criteria]
                    next[index] = { ...next[index], id: e.target.value }
                    setCriteria(next)
                  }}
                />
                <input
                  className={styles.criterionName}
                  type="text"
                  value={c.name}
                  onChange={(e) => {
                    const next = [...criteria]
                    next[index] = { ...next[index], name: e.target.value }
                    setCriteria(next)
                  }}
                />
                <input
                  className={styles.criterionMax}
                  type="number"
                  min={1}
                  max={5}
                  value={c.max}
                  onChange={(e) => {
                    const value = Number(e.target.value) || 0
                    const next = [...criteria]
                    next[index] = { ...next[index], max: value }
                    setCriteria(next)
                  }}
                />
              </div>
            ))}
          </div>
          <button type="button" className={styles.addCriterion} onClick={handleAddCriterion}>
            + Add Criterion
          </button>
        </section>
      </section>

      <section className={styles.outputGrid} aria-label="Generated JSON">
        <section className={styles.card}>
          <h2>Rubric JSON</h2>
          <pre className={styles.code}>{JSON.stringify(rubricJson, null, 2)}</pre>
        </section>
        <section className={styles.card}>
          <h2>Exam Configuration JSON</h2>
          <pre className={styles.code}>{JSON.stringify(examConfigJson, null, 2)}</pre>
        </section>
      </section>

      <section className={styles.submitRow}>
        <button type="button" className={styles.submitButton} onClick={handleSubmitToBackend}>
          Create Assessment
        </button>
        {submitStatus ? (
          <p className={styles.submitStatus} aria-live="polite">
            {submitStatus}
          </p>
        ) : null}
      </section>
    </main>
  )
}
