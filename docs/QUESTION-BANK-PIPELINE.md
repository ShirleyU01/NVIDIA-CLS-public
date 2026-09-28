# Question Bank Pipeline — Design (Socrates)

This document specifies a **multi-stage, checkpointed pipeline** that turns course materials (PDFs, etc.) into a **question bank** suitable for oral exams and for the **central backend**. It is written to be **implementation-ready**: concrete paths, job contracts, JSON shapes, and alignment with existing code in this repository.

**Implementation in this repo:** Python package [`question_bank/`](../question_bank/) with CLI modules `ingest` … `export`, sample parsed JSON under [`question_bank/fixtures/sample_parsed/`](../question_bank/fixtures/sample_parsed/), and `pip install -r question_bank/requirements.txt`. Default orchestrator: `python -m question_bank.pipeline --course CS109` stops after **retrieve**; use `--through export` for the full LLM path (requires `OPENAI_API_KEY`).

**Small test run:** (1) Fewer questions: `python -m question_bank.pipeline --course CS109 --through export --num-questions 2 --reasoning-effort medium` (or run `generate_questions` alone with `--num-questions 2`). (2) Separate output tree: set **`QUESTION_BANK_DATA_ROOT`** to e.g. `question_bank_test_data` (absolute or repo-relative); all stages read/write under that root instead of `question_bank_data/`. (3) Optional: use `--course CS109_test`, PDFs under `question_bank_data/raw/CS109_test/`, and a matching topics file `question_bank/configs/cs109_test_topics.yaml` (copy of `cs109_topics.yaml` with `course:` updated) so production `question_bank_data/` paths stay untouched even without the env var.

**Related code (read before implementing):**

- Jetson oral runtime: `jetson_runtime/run_exam.py`, `jetson_runtime/proctor.py` (`conduct_exam`, per-question `text` / `rubric_items` / `max_follow_ups`).
- Example exam JSON: `jetson_runtime/exams/example_exam.json`.
- Central API: `backend/routes/rubrics.py`, `backend/routes/question_sets.py`, `backend/routes/assessments.py`; Pydantic shapes in `backend/schemas.py`.
- Teacher UI exam shape (reference): `web/src/pages/TeacherCreateExamPage.tsx`.
- Rubric fixture shape: `integration/fixtures/rubric_bayes_oral_v1.json`.

---

## 1. Goals

1. **Reproducibility:** Each stage reads prior checkpoints from disk and writes the next artifact. Failed chunking does not force re-parsing PDFs.
2. **Debuggability:** Small scripts or modules per stage; logs and optional JSONL evaluation traces.
3. **Cost control:** Rule-based chunking (no LLM for Job B). Retrieval and generation use LLM/embeddings only where defined.
4. **Downstream compatibility:** Final artifacts must include a form that **`OralExamProctor.conduct_exam`** accepts, and an optional path to **create rubric + question set + assessment** on the central backend (three POSTs; see §10).

Non-goals for v1: scanned PDF OCR, instructor approval UI, Prefect/Airflow (orchestration stays a single `pipeline.py` + stage CLIs).

---

## 2. Design principles

- **Automate the pipeline, not one mega-prompt:** Deterministic ingest and chunking, versioned configs, structured generation, explicit validation.
- **Canonical vs export schema:** Store a **rich canonical** question record (expected answer, source chunk ids, structured rubric). **Export** maps that to the **flat** `rubric_items` list the proctor uses today, without changing `proctor.py` in v1.
- **Vector store (v1):** **FAISS (CPU) + sidecar metadata** under `question_bank_data/embeddings/`. No Postgres/pgvector requirement. Implement a narrow interface (e.g. `build_index`, `search(query_embedding, k)`) so pgvector can replace FAISS later without rewriting Jobs D–F.

---

## 3. Repository layout (concrete)

Proposed **new** tree (code colocated under `question_bank/` to avoid a generic top-level `src/`):

```
question_bank/
  __init__.py
  pipeline.py              # Orchestrator: --course, --from <stage>, optional dry-run
  ingest.py                  # Job A CLI
  chunk.py                   # Job B CLI
  embed.py                   # Job C CLI
  retrieve_topics.py         # Job D CLI
  generate_questions.py      # Job E CLI
  evaluate_questions.py      # Job F CLI
  export.py                  # Canonical → exam JSON + merged bank files
  upload_backend.py          # POST rubric, question-set, assessment
  parse_pdf.py               # PyMuPDF helpers
  chunking_rules.py          # Deterministic splitters by document_type
  schemas.py                 # Pydantic models for chunks, questions, evaluation
  faiss_index.py             # FAISS + metadata I/O
  llm.py                     # Thin wrapper; can delegate to integration/evidence_packet/llm_openai.py pattern
  paths.py                   # Resolve question-bank data dirs from course id + repo root
  requirements.txt           # pymupdf, faiss-cpu, numpy, pyyaml (optional install)
  configs/
    prompts.yaml             # System/user templates by generation batch type
    cs109_topics.yaml        # Example: course id, topics with aliases (add more courses as needed)
```

**Data** (at repo root; large/binary and raw PDFs should be gitignored):

```
question_bank_data/
  raw/
    <COURSE>/
      lectures/              # PDFs, optional subfolders
      exams/
      solutions/
      review/
      topics.txt             # Optional free-text topic hints (not replacing YAML)
  parsed/                    # One JSON per ingested source file
  chunks/
    chunks.jsonl             # Single appendable stream OR per-course chunks-<course>.jsonl
  embeddings/
    <COURSE>/
      index.faiss            # Or .index per convention
      chunks_meta.json       # Ordered list: { chunk_id, offset, ... } aligned FAISS row i
      manifest.json          # embedding model id, dim, course, source jsonl hash (for cache invalidation)
  topic_contexts/
    <COURSE>/
      <topic_id>.json        # Retrieved bundle for one topic
  generated_questions/
    <COURSE>/
      <topic_id>.json        # Draft model output per topic
  final_question_bank/
    <COURSE>/
      <topic_id>.json        # Validated subset per topic
      merged_bank.json       # Optional single file for handoff
```

**.gitignore** (add if missing): `question_bank_data/raw/**/*.pdf`, large `*.faiss`, optional entire `question_bank_data/raw/` for privacy.

---

## 4. Runtime and API contracts (this repo)

### 4.1 `conduct_exam` input (`exam_config` dict)

From `jetson_runtime/proctor.py`, the proctor expects at minimum:

| Key | Use |
|-----|-----|
| `exam_id` | Session id (generated if missing). |
| `subject` | Logged and stored in `exam_data` (use for display; teacher UI sometimes uses `title` — export can set **both** `subject` and `title` to the same string for compatibility). |
| `system_prompt` | Proctor / examiner behavior. |
| `lecture_material` | Optional string; passed into per-question flow for follow-ups and grading context. |
| `post_exam_follow_ups` | Int; whole-exam follow-ups (default 2 in examples). |
| `questions` | List of objects with **`text`**, **`rubric_items`** (list of strings), optional **`max_follow_ups`** (int), optional **`id`**. |

Reference: `jetson_runtime/exams/example_exam.json`.

### 4.2 Central backend

- `POST /rubrics` — body: `title`, optional `subject`, `rubric_json` (dict).
- `POST /question-sets` — body: `title`, optional `subject`, `question_set_json` (dict; typically the same shape as exam JSON the teacher builds).
- `POST /assessments` — body: `rubric_id`, `question_set_id`, `title`, optional `description`.

**Important:** An assessment **always** requires both a rubric row and a question set row. Upload automation must create rubric first (or accept an existing `rubric_id`), then question set, then assessment.

There is **no auth** on these routes in the current MVP; document that upload scripts are for trusted networks only.

---

## 5. Job A — Ingest materials

**Purpose:** Normalize heterogeneous files into structured parsed documents (text + provenance).

**Input:**

- `question_bank_data/raw/<COURSE>/lectures/*.pdf` (and exams, solutions, review per layout above).
- Optional manifest file listing inclusion/exclusion (future).

**Processing:**

- Primary extractor: **PyMuPDF** (`fitz`) for text and **page boundaries**.
- Record: `source_path`, `relative_path`, `sha256`, `course`, `document_role` (inferred from parent folder: `lecture`, `exam`, `solution`, `review`), `pages[]` each with `page_index`, `text`, optional `bbox`-free char count.

**Output (per file):**

- `question_bank_data/parsed/<slug>.json` where `slug` is filesystem-safe derived from path + short hash if needed to avoid collisions.

**Example top-level parsed JSON fields:**

```json
{
  "course": "CS109",
  "document_role": "exam",
  "source_path": "question_bank_data/raw/CS109/exams/midterm_2024.pdf",
  "sha256": "...",
  "title_guess": "Midterm 2024",
  "pages": [
    { "page_index": 0, "text": "..." }
  ],
  "ingested_at": "2026-04-17T12:00:00Z"
}
```

**CLI:** `python -m question_bank.ingest --course CS109 [--only lectures]`

**Idempotency:** Skip re-parse if output exists and `sha256` matches (store hash in parsed JSON).

---

## 6. Job B — Chunk and label

**Purpose:** Deterministic chunks with stable ids and metadata. **No LLM.**

**Input:** All `question_bank_data/parsed/*.json` for the course (filter by `course` field).

**Document type detection:**

- From `document_role` + filename heuristics (e.g. `solution` in name).
- Optional: first-page keywords (“Midterm”, “Practice”, etc.).

**Rules (v1):**

| Type | Strategy |
|------|----------|
| `lecture` | One **page** = one chunk; if `len(text) < N` chars, optionally merge with next page (configurable `N`). |
| `exam` / `solution` | Split on question boundaries: lines matching `^\\d+\\.`, `^Q\\d+`, subparts `\\([a-z]\\)`, etc. Config per course in YAML if patterns differ. |
| `review` | Split on markdown-style `#` / `##` headings; if chunk still huge, split paragraphs with max char limit. |

**Output:** `question_bank_data/chunks/chunks.jsonl` (or `question_bank_data/chunks/CS109.jsonl`) — **one JSON object per line**.

**Example JSONL line:**

```json
{
  "chunk_id": "CS109_exam_midterm2024_q3a",
  "course": "CS109",
  "source_type": "exam_question",
  "document_name": "Midterm 2024",
  "source_path": "question_bank_data/raw/CS109/exams/midterm_2024.pdf",
  "parsed_slug": "midterm_2024",
  "page_span": [2, 2],
  "question_id": "3a",
  "topic_hint": null,
  "text": "Suppose X and Y are independent..."
}
```

**`chunk_id` stability:** Hash or deterministic join of `(course, source_path or parsed_slug, question_id or page_span)`.

**CLI:** `python -m question_bank.chunk --course CS109`

---

## 7. Job C — Embed and index

**Purpose:** Vector index over all chunks for the course.

**Input:** Course-filtered lines from `chunks.jsonl`.

**Processing:**

- Batch call embedding API (OpenAI or configurable); store **model name and dimension** in `manifest.json`.
- Normalize vectors as required by FAISS inner product / L2 choice (document in manifest; typical: L2 + IndexFlatIP with normalized embeddings, or IndexFlatL2).

**Output:**

- `question_bank_data/embeddings/<COURSE>/index.faiss` (or equivalent).
- `question_bank_data/embeddings/<COURSE>/chunks_meta.json`: array index `i` ↔ `{ "chunk_id": "...", ... }` aligned with FAISS row order.
- `question_bank_data/embeddings/<COURSE>/manifest.json`: `embedding_model`, `dim`, `chunk_file_sha256`, `num_vectors`, `created_at`.

**CLI:** `python -m question_bank.embed --course CS109 [--force]`

**Idempotency:** If manifest exists and input chunk file hash unchanged, skip unless `--force`.

---

## 8. Job D — Retrieve by topic

**Purpose:** Build a **topic bundle**: the text the generator will see for each syllabus topic.

**Input:**

- `question_bank/configs/<course>_topics.yaml` (see §12).
- FAISS index + metadata from Job C.

**Query generation (templated, no LLM):**

For each topic, build a list of strings, e.g.:

- `"{name} definition"`
- `"{name} worked example"`
- `"{alias} exam problem"` for each alias
- Fixed templates from YAML: `common_mistakes`, `intuition`, etc.

Embed each query, retrieve **top_k** (e.g. 8) per query, **union** results, **dedupe** by `chunk_id`, optional **MMR**-style diversity (future). Cap total chunks per topic (e.g. 40).

**Output:** `question_bank_data/topic_contexts/<COURSE>/<topic_id>.json`

**Example file structure:**

```json
{
  "course": "CS109",
  "topic_id": "conditional_probability",
  "topic_name": "Conditional Probability and Bayes Rule",
  "queries_used": ["conditional probability definition", "bayes rule", "..."],
  "chunks": [
    {
      "chunk_id": "CS109_lec05_p12",
      "text": "...",
      "source_type": "lecture",
      "document_name": "Lecture 05",
      "score": 0.82
    }
  ],
  "built_at": "2026-04-17T12:30:00Z"
}
```

**CLI:** `python -m question_bank.retrieve_topics --course CS109`

---

## 9. Job E — Generate questions

**Purpose:** LLM generates **structured JSON only** (no free prose) in **small batches** to reduce duplication and improve debuggability.

**Input:** One `question_bank_data/topic_contexts/<COURSE>/<topic_id>.json` per invocation (or loop inside CLI).

**Batch types (separate prompt templates in `prompts.yaml`):**

- `conceptual` (e.g. 5 items)
- `computational` (e.g. 5)
- `misconception` (e.g. 5)
- `oral` / short spoken style (e.g. 5)

Each batch call includes: topic metadata, concatenated chunk excerpts (respect token budget; truncate longest chunks with ellipsis marker), and a **JSON schema** or Pydantic-constrained output.

**Canonical draft question object (per item):**

```json
{
  "question_id": "CS109_condprob_concept_001",
  "course": "CS109",
  "topic_id": "conditional_probability",
  "question_type": "conceptual",
  "difficulty": "easy",
  "question": "What does P(A|B) represent in words?",
  "expected_answer": "The probability that A occurs given that B has occurred.",
  "source_chunk_ids": ["CS109_lec05_p12"],
  "hints": [
    "Think about what information is being treated as already known.",
    "Restrict attention to the outcomes where B occurred before reasoning about A.",
    "Use the conditional probability relationship, but leave the final wording to the student."
  ],
  "rubric": {
    "full_credit": ["States conditioning on B occurred", "Interprets as restricted sample space"],
    "partial_credit": ["Gives formula only without interpretation"],
    "common_mistakes": ["Confuses P(A|B) with P(B|A)"]
  },
  "follow_ups": [
    { "condition": "correct", "question": "How does this relate to independence?" },
    { "condition": "incorrect", "question": "What is the definition of joint probability?" }
  ]
}
```

**Output:** `question_bank_data/generated_questions/<COURSE>/<topic_id>.json` — array or `{ "topic_id", "questions": [...] }` with merge of all batch types.

**CLI:** `python -m question_bank.generate_questions --course CS109 [--topic conditional_probability]`

---

## 10. Job F — Evaluate and filter

**Purpose:** Drop or flag bad items; optional single retry with a fix instruction.

**Checks:**

1. **Schema / rules:** required fields, max lengths, `source_chunk_ids` nonempty and each id exists in topic bundle.
   Canonical questions should include exactly three progressive `hints`, ordered from least to most revealing, without stating the final answer.
2. **Topic alignment:** optional LLM judge with strict JSON: `{ "on_topic": bool, "answerable_from_context": bool, "notes": "" }`.
3. **Near-duplicate:** embedding cosine similarity against other accepted questions in the same run; threshold e.g. 0.92 → reject or merge.
4. **Difficulty sanity:** optional heuristic (length, jargon) + optional judge score 1–5.

**Output:**

- `question_bank_data/final_question_bank/<COURSE>/<topic_id>.json` — only accepted questions (canonical shape).
- `question_bank_data/final_question_bank/<COURSE>/evaluation_log.jsonl` — one line per candidate with scores, reject reasons, retry generations.

**Regeneration (v1, limited):**

- If reject reason in `{duplicate, vague, off_topic}`, one retry with appended instruction citing reason; cap retries per `question_id` base.

**CLI:** `python -m question_bank.evaluate_questions --course CS109`

**Legacy hint backfill:** To add or refresh three progressive hints on an already-generated bank without regenerating the questions, run the deterministic fallback:

```bash
python -m question_bank.backfill_hints --course CS109 --target final
python -m question_bank.export --course CS109
```

For higher-quality hints, call the configured generation LLM on existing questions:

```bash
python -m question_bank.backfill_hints --course CS109 --target final --mode llm --overwrite
python -m question_bank.export --course CS109
```

Use `--target both` to update both `generated_questions` and `final_question_bank`, `--limit N` to test a small batch first, `--model` to override the course config model, and `--overwrite` to replace existing hints.

---

## 11. Export — canonical to Socrates / backend shapes

**Purpose:** Produce artifacts humans and tools consume.

### 11.1 Proctor-ready `exam_config` JSON

Map each canonical question to:

- `text` ← `question`
- `rubric_items` ← ordered flattening of `rubric`, e.g.  
  `"Full credit: …; …"`, `"Partial credit: …"`, `"Common mistakes: …"`  
  (one string per bullet group, or one string per bullet — choose one convention and document it).
- `hints` ← canonical progressive hints for study-mode practice payloads; the oral proctor export may omit them if the exam flow should not expose hints.
- `max_follow_ups` ← from config default (e.g. 2) or per-question override if present.
- `id` ← stable `question_id`.

**`lecture_material` (optional):** Concatenate top-N retrieved chunk texts used across selected questions (deduped, truncated with header comments) so the proctor has inline context without reading FAISS.

Write e.g. `question_bank_data/final_question_bank/<COURSE>/export_exam_cs109_v1.json`.

### 11.2 Backend `rubric_json`

Must align with evidence / teacher patterns: `rubric_id`, `scale`, `criteria[]` with `id`, `name`, `description`, `max`, `anchors`, `weight`. Two practical options:

- **Course template:** One rubric per export with criteria that apply globally to the oral (communication, reasoning depth, etc.), **or**
- **Synthesized criteria:** Map recurring canonical rubric dimensions into criteria (harder; phase later).

v1 recommendation: **course-level oral rubric template** in `configs/` plus static `criteria`; grading still uses `rubric_items` strings at question level inside `question_set_json` for the proctor.

### 11.3 Upload script (`upload_backend.py`)

Environment/config: `CENTRAL_API_BASE_URL` (e.g. `http://127.0.0.1:8000`).

Sequence:

1. `POST {base}/rubrics` → save `rubric_id` from response.
2. `POST {base}/question-sets` with `question_set_json` = exported exam JSON → save `question_set_id`.
3. `POST {base}/assessments` with both ids + `title` / `description`.

Flags: `--dry-run` (print bodies only), `--base-url`, `--skip-assessment` (stop after question set).

---

## 12. Topic configuration (no hardcoded topics in prompts)

**File:** `question_bank/configs/cs109_topics.yaml` (one per course or shared with overrides).

**Example:**

```yaml
course: CS109
embedding_model: text-embedding-3-small
generation_model: gpt-5.4
retrieve:
  top_k_per_query: 8
  max_chunks_per_topic: 40
topics:
  - id: probability_basics
    name: Probability Basics
    aliases:
      - sample space
      - events
      - axioms of probability
    query_templates:
      - "{name} definition"
      - "{name} example"
      - "{alias} practice problem"

  - id: conditional_probability
    name: Conditional Probability and Bayes Rule
    aliases:
      - conditional probability
      - bayes rule
      - bayes theorem
    query_templates:
      - "{name} intuition"
      - "{alias} exam problem"
```

Prompts stay in **`prompts.yaml`**; Python loads topic ids/names from this file only.

---

## 13. Orchestration (`pipeline.py`)

**Example:**

```bash
python -m question_bank.pipeline --course CS109
python -m question_bank.pipeline --course CS109 --from embed   # skip ingest/chunk if artifacts valid
```

**Behavior:**

- Run stages A→F in order (or from `--from`).
- After F, run `export` (same process or subprocess).
- Optional `--upload` to invoke `upload_backend.py` with same base URL.

**Manifest (recommended):** `question_bank_data/.pipeline_state/<COURSE>.json` storing per-stage `{ "completed_at", "input_hash" }` so reruns are cheap and auditable.

---

## 14. Dependencies

Add `question_bank/requirements.txt` (install when working on this feature):

- `pymupdf` — PDF text
- `faiss-cpu` — vector index (use `faiss-gpu` only if environment has CUDA and you explicitly want it)
- `numpy`
- `pyyaml`
- `openai` — already in repo root `requirements.txt`; reuse version constraints where possible

Root `requirements.txt` may stay minimal; document in this file that question bank developers run:

`pip install -r question_bank/requirements.txt`

---

## 15. Phased delivery

| Phase | Scope |
|-------|--------|
| **1** | Jobs A–D, `pipeline.py` up to topic contexts, FAISS + manifest. |
| **2** | Job E + canonical schema + `export.py` → proctor JSON on disk only. |
| **3** | Job F + dedup + limited retry + `evaluation_log.jsonl`. |
| **4** | `upload_backend.py` + rubric template wiring; optional richer follow-up trees consumed by future proctor changes (out of scope until contract is extended in code). |

---

## 16. Risks and limitations

| Risk | Mitigation |
|------|------------|
| Scanned PDFs (image-only) | v1 assumes text PDFs; document OCR as future dependency. |
| Bad splits on exams | Tune regex per course in YAML; keep human-readable `parsed` JSON for debugging. |
| API cost | Cache embeddings; skip embed when chunk file hash unchanged. |
| Backend has no auth | Run upload only on trusted networks; do not commit API URLs with secrets. |
| `title` vs `subject` | Export sets both to the same human-readable string where applicable. |
| Assessment needs rubric + question set | Upload script always implements the three-step create sequence. |

---

## 17. Quick traceability matrix

| Your pipeline stage | Artifact path (typical) |
|---------------------|-------------------------|
| Parsed docs | `question_bank_data/parsed/*.json` |
| Chunks | `question_bank_data/chunks/*.jsonl` |
| Index | `question_bank_data/embeddings/<COURSE>/index.faiss` + `chunks_meta.json` |
| Topic bundles | `question_bank_data/topic_contexts/<COURSE>/<topic_id>.json` |
| Drafts | `question_bank_data/generated_questions/<COURSE>/<topic_id>.json` |
| Validated | `question_bank_data/final_question_bank/<COURSE>/<topic_id>.json` |
| Jetson exam | `question_bank_data/final_question_bank/<COURSE>/export_exam_*.json` |
| Backend | Created rows via `upload_backend.py` |

This document is the **source of truth** for implementing the question bank; when code diverges, either update the code or update this document in the same change.
