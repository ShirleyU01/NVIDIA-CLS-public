# Question bank → Study mode integration plan

This document is a **concrete implementation plan** (no code changes yet) for wiring the existing **`question_bank/`** pipeline into the **study-mode** student flow, so students can pick a **topic**, choose **how many questions** to practice, and run through the **same capture / grade / follow-up / end study** UX with questions sourced from the bank instead of only from the assessment’s `exam_config.questions[0]`.

---

## 0. Resolved product decisions (v1)

These choices are **locked for implementation planning**:

| # | Topic | Decision |
|---|--------|----------|
| 1 | Question bank storage | **File-backed v1** — read from `question_bank_data/final_question_bank/<COURSE>/` (and `QUESTION_BANK_DATA_ROOT` when set). Bank is generated once offline; no Postgres question bank for v1. |
| 2 | Course scope | **Student course picker** on study prep — chosen `course_id` (e.g. `CS109`) drives which topics file and which `final_question_bank` directory are used. **Not** inferred from the row the student clicked on the assessments table (unless you later add a shortcut). |
| 3 | Selection policy | **Random without replacement**, with a **difficulty mix** rule so a set of *N* questions is not all one level when the pool allows it (see §0.1). |
| 4 | Advancing questions | **Dedicated “Next question”** control — calls `POST .../next-question`. **“I understand”** stays a lightweight acknowledgment / follow-up dismiss; it does **not** advance the index. |
| 5 | Assessment linkage | **Separate practice assessment** (or **`assessment_id` nullable** on `sessions` if the schema is extended). Practice runs are **not** tied to the same assessment_id as a graded oral exam. **Instructor UX (interim):** practice sessions still **appear in the same instructor assessments / session views as “exam” assessments** (no separate Practice tab required for v1) — e.g. by seeding a dedicated “Practice (Question bank)” assessment per course and attaching bank-study sessions to it, or by listing sessions with null assessment under a synthetic row; exact DB shape is an implementation detail but the **visible outcome** is one familiar list. |
| 6 | Dev without central | **Official recommendation in §0.2** — default to local central for bank study; optional Jetson-only dev mirror only if needed. |

### 0.1 Difficulty-aware random selection (concrete)

Canonical bank questions include `difficulty: str` in `question_bank/schemas.py` (`CanonicalQuestion`). Selection service should:

1. Load all validated questions for `(course_id, topic_id)` from the topic JSON file.
2. **Filter** to questions that pass the same validation / export mapping used elsewhere (flatten rubric, non-empty `text`).
3. If `count >= len(pool)`, return **entire pool** (shuffled or stable order — pick shuffled for v1 unless reproducibility tests need a seed).
4. If `count < len(pool)`:
   - **Group** pool by `difficulty` (normalize casing; treat unknown/empty as `"unspecified"` bucket).
   - **Allocate** counts per bucket so each non-empty bucket gets at least one question when `N` is large enough (e.g. greedy round-robin across sorted bucket keys until each has 1, then fill remaining slots uniformly at random from the whole pool without replacement).
   - If **some difficulty buckets are empty** (e.g. only `"medium"` exists), fill remaining slots from the whole pool at random.
5. **Shuffle** the final ordered list (or shuffle within strata then concatenate) so presentation order is not always easy → hard.

Document the exact allocation in code comments + unit tests (edge cases: single bucket, `N=1`, `N=2` with two buckets, pool smaller than bucket count).

### 0.2 Dev without central — official recommendation

**Context:** `web/src/api/studentStudyGuide.ts` has two behaviors today:

- **With** `VITE_CENTRAL_API_BASE_URL`: central session + `GET /assessments/{id}/exam-config` + Jetson study run.
- **Without** it (Vite + Jetson only): a synthetic `session_id` and **hard-coded** `question_text` + `rubric_items` on Jetson — no sessions API, **no** question-bank selection.

Once bank-based study ships, **course / topic / count / selection** live on the **central** plan (§4, §6). That code path must not be reimplemented in TypeScript as the primary dev loop (fixtures drift from real caps, difficulty rules, and validation).

**Official recommendation (lock this for the team):**

1. **Default:** Developers working on question-bank study mode run **local central** (same `backend/` as production: `POST /sessions`, question-bank routes, etc.) plus Jetson and Vite. Set `VITE_CENTRAL_API_BASE_URL` to that instance. This is the **supported** dev setup: one selection implementation, same contracts as deployed environments.

2. **Optional escape hatch (only if needed):** If someone must iterate on UI **without** central repeatedly, add **dev-only** read-only endpoints on Jetson that **reuse the same Python selection module** as central (shared `question_bank/select.py`, same `QUESTION_BANK_DATA_ROOT`), guarded by an env flag (e.g. `JETSON_DEV_QUESTION_BANK_MIRROR=1`). This is **not** a product API surface — it avoids duplicating business logic while unblocking edge cases.

3. **Avoid:** Large **frontend-only** mock topic/question lists as the main way to develop bank study — acceptable for a short spike, not as the default workflow.

**“Mock path”** in conversation means item **2** above (optional Jetson mirror or tiny fixtures), not a requirement parallel to central.

---

## 1. Current state (baseline)

### 1.1 Frontend study flow (today)

- **Prep:** `web/src/pages/StudentStudyPrepPage.tsx` — student clicks **Begin Study**; no topic/count UI.
- **API:** `web/src/api/studentStudyGuide.ts`
  - With central API: `GET /assessments/{id}/exam-config` → `exam_config` → `POST /sessions` → `POST /jetson/study-guide/runs` with `{ session_id, exam_config }`.
  - **Important:** Jetson study creation only uses the **first** question in `exam_config` (see below).
- **Session:** `web/src/pages/StudentStudySessionPage.tsx` — polls `getState`, **Capture & grade**, actions, **End Study** → review page.

### 1.2 Jetson study backend (today)

- File: `jetson_runtime/jetson_backend.py`
- `POST /jetson/study-guide/runs` accepts `CreateStudyRunRequest`: `session_id`, optional `exam_config`, or `question_text` + `rubric_items`.
- `_study_question_from_payload` **extracts only** `exam_config.questions[0]` (`text`, `rubric_items`).
- `_StudyRuntime` holds a **single** `question_text` / `rubric_items`.
- Captures land under `jetson_runtime/sessions/<session_id>/paper/` (`paper_<ts>.jpg` + feedback files).
- `POST .../end` calls `aggregate_study_session`, then `build_study_student_feedback` / `build_study_teacher_summary` with **one** `question_text` + `rubric_items` for the whole session.

### 1.3 Question bank (today)

- Package: `question_bank/` — topics in YAML (e.g. `question_bank/configs/cs109_topics.yaml` with `topics[].id` / `name`).
- Validated questions per topic: `question_bank_data/final_question_bank/<COURSE>/<topic_id>.json` (and `merged_bank.json` from export).
- Canonical → proctor shape: `question_bank/export.py` maps `CanonicalQuestion` → `{ id, text, rubric_items, max_follow_ups }`.

**Gap:** There is **no HTTP API** today that returns “N questions for topic X” to the browser; selection logic would be new (central or Jetson).

---

## 2. Target user experience

1. Student opens **Study prep** (`/student/study/prep?assessmentId=...`) and then clicks **Begin Study** to reach study configuration (`/student/study/config?assessmentId=...`); the `assessmentId` query param may become **optional** for bank-first practice (see §6 on practice assessment).
2. Student sees:
   - **Course** selector (student picker; drives bank path and topics list).
   - **Topic** selector (from that course’s topics YAML).
   - **Number of questions** (integer input or select; min/max documented, e.g. 1–10).
3. Student clicks **Begin Study** (same primary action; optionally rename to **Start practice** later).
4. **Study session** behaves as today for each question:
   - Show **current question** text and **“Question *i* of *N*”**.
   - **Capture & grade** → feedback markdown / JSON.
   - **I’m lost** / **I understand** / typed follow-up — same endpoints, prompts grounded on **current** question + latest feedback.
5. When the student finishes question *i* (*i* < *N*), they click **Next question** (§5.3); **I understand** does **not** advance.
6. **End Study** runs once after the student completes the full set (or explicitly ends early — policy in §5); post-session **student + teacher** summaries still post to central as today, but content must reflect **all questions** (or all completed — policy).

---

## 3. Design principles

1. **Minimize parallel flows** — One study session id; one paper artifact directory tree; extend state instead of spawning N Jetson runs per “practice set”.
2. **Reuse proctor-shaped payloads** — Prefer reusing `{ text, rubric_items, id? }[]` already produced by `question_bank/export.py` logic (flattened rubric strings).
3. **Explicit contracts** — Pydantic models / TypeScript types for “practice plan” `{ course, topic_id, question_ids[] }` stored in session storage or returned from create-run.
4. **Backward compatibility** — If topic/count omitted, behavior matches **today** (assessment `exam_config` first question only).
5. **Observability** — Log selected `question_id`s and topic for debugging; optional persist on central session row or artifacts.

---

## 4. Recommended architecture (v1)

### 4.1 Where selection runs

**Recommendation:** Implement **question selection on the central backend** (new read-only endpoints), because:

- The browser already talks to central for `exam-config` and `POST /sessions`.
- `question_bank` is Python and colocated with `backend/`; can import small selection helpers without duplicating logic in TypeScript.
- Jetson stays responsible for **runtime** (camera, grading LLM, aggregation upload).

**Alternative (acceptable):** Implement selection on **Jetson** by bundling a copy of `question_bank_data/final_question_bank/` on device and adding `GET /jetson/study-guide/question-bank/...` — fewer moving parts if central is not deployed, but duplicates deployment of bank files.

### 4.2 How questions reach Jetson

**Recommendation:** Extend `POST /jetson/study-guide/runs` body with an optional field:

```json
{
  "session_id": "<central-session-uuid>",
  "practice_questions": [
    { "id": "cs109_q_...", "text": "...", "rubric_items": ["..."] }
  ]
}
```

Semantics:

- If `practice_questions` is **non-empty** → study runtime uses this list (ignore `exam_config` for question text, or use `exam_config` only for optional global metadata later).
- If absent / empty → **existing** behavior: `exam_config` or `question_text` + `rubric_items`.

This avoids shipping the entire merged bank to the client and keeps a single source of truth from central selection.

---

## 5. Multi-question study runtime (Jetson)

### 5.1 Runtime model

Extend `_StudyRuntime` (conceptually; names TBD in implementation):

| Field | Purpose |
|--------|--------|
| `questions: list[StudyQuestion]` | Full ordered list (N items). |
| `current_index: int` | 0-based; drives `questionText` / `rubric_items` in state. |
| `status`, `thread`, capture fields | Unchanged pattern per capture. |

`StudyRunState` (FastAPI response model) should gain optional fields for the UI, for example:

- `questionIndex` (1-based) and `questionCount`, **or** only expose in frontend from cached plan — **prefer API fields** so refresh/recovery works without extra client state.

### 5.2 Capture / feedback files and aggregation

Today `jetson_runtime/study_guide/feedback_aggregation.py` notes that **per-capture** `paper_<ts>.json` / `.md` should pair with images; until all captures use per-ts files, aggregation may mis-associate feedback for **multiple questions**.

**Required for multi-question v1:**

- On each successful grade for question *k*, write feedback to **`paper_<same_ts>.json` and `paper_<same_ts>.md`** next to `paper_<ts>.jpg` (same timestamp as capture).
- Optionally nest captures: `paper/q<k>/paper_<ts>.jpg` — clearer for humans and aggregation; **pick one convention** and update `aggregate_study_session` to return ordered records that include **question index** (new field on `CaptureRecord` or parallel structure).

### 5.3 Advancing to the next question

Options (pick one in implementation):

| Option | Pros | Cons |
|--------|------|------|
| **A. New endpoint** `POST /jetson/study-guide/runs/{id}/next-question` | Explicit, idempotent-ish, easy to reason about | Extra API surface |
| **B. Overload** `action: "understand"` to advance when at terminal state | No new route | Couples “dismiss” and “advance”; may confuse if student wants to re-read feedback |

**Decision (locked):** **Option A** — `POST .../next-question` validates `current_index < N-1`, clears transient UI fields (`feedback_md`, `followup_md`, `error`), resets status to `idle`, increments index. **“I understand” must not advance** the question index (§0).

### 5.4 End study and LLM summaries

`end_study_run` currently passes a **single** `question_text` / `rubric_items` into:

- `build_study_student_feedback`
- `build_study_teacher_summary`

**Plan change:**

- Either **extend builders** to accept `list[{question_text, rubric_items, captures_subset}]`, **or** build a **synthetic combined prompt** that iterates questions and attaches capture records grouped by question (cleaner for teacher narrative).

**Artifact contract:** Keep central payload keys `study_feedback` and `study_teacher_summary`; **version** the JSON shape inside (e.g. `schema_version: 2`, `questions: [...]`) so `TeacherStudyFeedback` / `StudentStudyReviewPage` can render multi-question results without breaking v1 consumers (feature-detect on `schema_version` or presence of `questions` array).

---

## 6. Central backend work

### 6.1 New endpoints (concrete)

Proposed routes (names illustrative; align with `backend/main.py` router style):

1. **`GET /question-bank/courses`**  
   - Returns `[{ "id": "CS109", "title": "CS109 Probability" }]`.  
   - Source: static config file listing courses that have `question_bank_data/final_question_bank/<COURSE>/`, or env `QUESTION_BANK_ENABLED_COURSES`.

2. **`GET /question-bank/courses/{course_id}/topics`**  
   - Returns topics mirroring YAML: `[{ "id": "conditional_probability", "name": "Conditional Probability and Bayes Rule" }]`.  
   - Implementation: read `question_bank/configs/{course}_topics.yaml` or a copied JSON artifact under `question_bank_data/` generated at export time.

3. **`POST /question-bank/courses/{course_id}/selection`**  
   - Body: `{ "topic_id": "...", "count": 5, "seed": 12345 optional }`  
   - Response: `{ "questions": [ { "id", "text", "rubric_items", "difficulty"? } ] }` (optional `difficulty` for debugging / UI badges).  
   - Implementation:
     - Load `question_bank_data/final_question_bank/<COURSE>/<topic_id>.json`.
     - Parse `questions[]` through existing `CanonicalQuestion` validation where possible; map to flattened `rubric_items` using same rules as `export.flatten_rubric`.
     - Sample `count` questions using **§0.1** (random + difficulty mix).
   - Errors: 404 if topic file missing; 400 if `count` > available.

### 6.2 Session metadata (optional but useful)

When creating `POST /sessions` for bank-driven study:

- Use the **practice assessment** id (or `assessment_id: null` if the schema supports it and the UI can still list the session — prefer a real practice assessment row for interim “looks like exam” instructor listing per §0).
- Extend body (backward compatible) with optional `device_info` — e.g. `device_info: { ..., "mode": "study", "source": "web-student-ui", "study_plan": { "course", "topic_id", "requested_count", "question_ids" } }`.

If altering DB rows is undesirable in v1, store **`study_plan` only client-side** and rely on artifacts at end — weaker for teacher analytics.

### 6.3 Security / abuse

- Rate-limit `selection` if exposed publicly.
- Validate `count` upper bound server-side.
- Do not return full course merged bank in one response.

---

## 7. Frontend work

### 7.1 `StudentStudyPrepPage`

- Add **course** (student picker), **topic** `<select>`, **count** `<input type="number">` or select.
- Load topics via new `teacherApi` or dedicated `questionBankApi` module (e.g. `web/src/api/questionBank.ts`).
- On **Begin Study**:
  1. `POST /question-bank/.../selection` with `{ topic_id, count }`.
  2. `POST /sessions` (existing) with **practice `assessment_id`** (or nullable per backend) — include `study_plan` in `device_info`.
  3. `POST /jetson/study-guide/runs` with `{ session_id, practice_questions: [...] }` (and omit `exam_config` **or** send minimal `exam_config` for compatibility during transition — decide in impl.).
- Persist in `sessionStorage` (alongside existing `study:assessmentId:${sessionId}`):
  - `study:plan:${sessionId}` = JSON stringified `{ course, topicId, questionIds, questionCount }` for recovery.

### 7.2 `studentStudyGuide.ts`

- Extend `CreateStudyRunRequest` with optional `courseId`, `topicId`, `questionCount`, and/or pass pre-fetched `practiceQuestions` from the page.
- Update `ensureRun` path: if recovering, re-POST Jetson create with **same** `practice_questions` list (central may need to echo stored plan, or client re-fetches selection — **re-fetch can change questions**; prefer **storing plan on central session** or re-sending from sessionStorage).

### 7.3 `StudentStudySessionPage`

- Display **Question i of N** from API state.
- After student reads feedback, show **Next question** button calling `POST .../next-question`, disabled while capture in progress.
- On last question, hide **Next**; **End Study** unchanged.
- Error handling: if Jetson returns 400 “no more questions”, sync UI index.

### 7.4 Review / teacher UI

- If post-session JSON becomes multi-question, update:
  - `web/src/pages/StudentStudyReviewPage.tsx`
  - `web/src/components/TeacherStudyFeedback.tsx`
- **Plan:** render a **list of rubric sections per question** when `schema_version >= 2`; else keep current single-question layout.

---

## 8. Question bank package touchpoints (minimal)

- **Reuse** `question_bank/schemas.py` + `export.flatten_rubric` from central (import path: ensure `backend` venv includes repo root on `PYTHONPATH`, or copy a thin `question_bank` dependency into backend container).
- Add `question_bank/select.py` (recommended) with pure function `select_questions(course, topic_id, count, rng)` implementing **§0.1**, used by `backend/routes/question_bank.py` and unit tests.
- **Tests:** unit tests for selection edge cases (count > pool, empty pool, invalid topic, single-bucket difficulty, multi-bucket stratification).

---

## 9. Deployment & ops

1. **Data sync:** Ensure `question_bank_data/final_question_bank/<COURSE>/` exists on the **machine running the central API** (or mount volume / bake into image for class pilots).
2. **Jetson:** No change to bank files if selection is central-only; only receives N question payloads.
3. **Config:** `QUESTION_BANK_DATA_ROOT` alignment between pipeline runs and server read path (same as pipeline doc).
4. **Feature flag:** e.g. `VITE_ENABLE_QUESTION_BANK_STUDY=true` to hide UI until backend is wired.

---

## 10. Phased rollout (concrete milestones)

| Phase | Scope | Exit criteria |
|-------|--------|----------------|
| **P0** | Central selection API + unit tests | Curl/browser can fetch topics and N questions for CS109 demo topic |
| **P1** | Jetson accepts `practice_questions[]`, multi-index state + `next-question` | Manual: 2-question run, two captures, distinct feedback per question on disk |
| **P2** | Frontend prep + session UX + sessionStorage recovery | Student can complete N questions end-to-end |
| **P3** | `end_study_run` aggregation + summary JSON v2 + review/teacher UI | Post-session shows all questions; central artifacts accepted |
| **P4** | Polish: practice assessment seeding / instructor list behavior, analytics, rate limits | Practice sessions visible like exams; basic limits |

---

## 11. Testing checklist (manual + automated)

- **API:** selection returns stable shape; 404/400 paths.
- **Jetson:** create with `practice_questions` length 1 (parity with old), 3, 10.
- **Concurrency:** double `capture` while `thinking` still rejected.
- **Recovery:** refresh mid-session; `ensureRun` restores same questions.
- **Central:** `GET /sessions/{id}` after end includes `study_feedback` with expected schema.
- **Regression:** study flow **without** topic/count still uses assessment first question.

---

## 12. Open risks

1. **LLM cost** scales with **N × (captures + summaries)**; cap `N` in product.
2. **Teacher summary quality** may degrade if N is large — may need chunking or two-pass summary.
3. **Assessment vs bank rubric mismatch** — bank questions may not match instructor assessment; communicate “practice” vs “graded assessment” in UI copy.

---

## 13. Related documents

- [`QUESTION-BANK-PIPELINE.md`](./QUESTION-BANK-PIPELINE.md) — data layout, export shapes.
- [`FRONTEND-FLOW.md`](./FRONTEND-FLOW.md) — current routes and APIs (update after implementation).
- [`BACKEND-INTEGRATION-PLAN.md`](./BACKEND-INTEGRATION-PLAN.md) — align new endpoints with broader integration narrative.

When this feature ships, add a short subsection there and a delta section in `FRONTEND-FLOW.md` pointing to study prep + new APIs.
