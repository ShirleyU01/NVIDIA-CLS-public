## Backend + Database Integration Plan

This document describes a concrete implementation plan for wiring a real backend and database into the existing codebase, aligned with `SYSTEM-DESIGN.md`, `jetson_runtime/`, `integration/`, and the React app in `web/`.

The goal is to:

- Provide a minimal but real **central backend** for teachers and sessions.
- Add a thin **Jetson-local backend** that wraps `jetson_runtime/proctor.py`.
- Persist data in a **PostgreSQL** database, with JSONB for flexible structures (rubrics, evidence packets).
- Reuse the existing evidence-packet pipeline in `integration/`.

---

## 1. Technology Choices

- **Backend framework (central + Jetson):**
  - Python **FastAPI** (async, typed, great JSON APIs, easy to integrate with existing Python code).

- **Database:**
  - **PostgreSQL** as the primary relational store.
  - Use **JSONB** columns for:
    - Rubric JSON.
    - Question-set / materials JSON.
    - Evidence packet JSON.
    - Optional extra metadata blobs.

- **ORM / models:**
  - Use **SQLAlchemy** (with Pydantic models for request/response schemas), or **SQLModel** if we want a simpler Pydantic-first layer.

- **Job / background processing:**
  - Start with simple in-process **FastAPI background tasks** for evidence packet generation.
  - If/when needed, move to a separate worker using **RQ** or **Celery** with Redis.

---

## 2. High-Level Topology

We will have two Python services:

- **Central backend** (cloud or campus server):
  - Owns relational data (rubrics, question sets, assessments, sessions, reviews).
  - Owns evidence-packet generation jobs (using `integration/`).
  - Serves teacher UI and central APIs.

- **Jetson-local backend** (on-device, small FastAPI app):
  - Wraps `jetson_runtime/proctor.py` (`OralExamProctor`) and `session_manager.py`.
  - Exposes the `/jetson/exams` HTTP endpoints described in `SYSTEM-DESIGN.md`.
  - Communicates with the **central backend** for `/sessions` and `/sessions/{id}/artifacts`.

The React app in `web/` will:

- Point teacher-facing routes to the **central backend**.
- Point student-facing routes (on Jetson) to the **Jetson-local backend**, which proxies to the central backend as needed.

---

## 3. Data Model (Central Backend)

Implement the following relational tables in PostgreSQL (schemas are illustrative, not exhaustive):

- **`users`**
  - `id` (PK, UUID or serial)
  - `role` (`teacher`, `student`, `admin`)
  - `email`, `name`
  - `created_at`, `updated_at`

- **`rubrics`**
  - `id` (PK)
  - `owner_id` (FK → `users.id`)
  - `title`, `subject`
  - `rubric_json` (JSONB; structure like `integration/fixtures/rubric_bayes_oral_v1.json`)
  - `created_at`, `updated_at`

- **`question_sets`**
  - `id` (PK)
  - `owner_id` (FK → `users.id`)
  - `title`, `subject`
  - `question_set_json` (JSONB; questions and sections)
  - `created_at`, `updated_at`

- **`assessments`**
  - `id` (PK)
  - `owner_id` (FK → `users.id`)
  - `rubric_id` (FK → `rubrics.id`)
  - `question_set_id` (FK → `question_sets.id`)
  - `title`, `description`, `status` (`draft`, `published`, `archived`)
  - `publish_settings` (JSONB; optional start/end dates, visibility)
  - `created_at`, `updated_at`

- **`sessions`**
  - `id` (PK; aligns with Jetson `session_id` naming)
  - `assessment_id` (FK → `assessments.id`)
  - `student_id` (FK → `users.id`, nullable / anonymous)
  - `started_at`, `ended_at`
  - `device_info` (JSONB; optional Jetson metadata)
  - `artifacts` (JSONB; URIs/paths for `recording.mp4`, `final_transcript.json`, `session_json`, etc.)
  - `status` (`created`, `running`, `completed`, `evidence_pending`, `evidence_ready`, `reviewed`)
  - `evidence_packet_status` (`pending`, `processing`, `ready`, `error`)
  - `score_total` (numeric), `score_max` (numeric)
  - `created_at`, `updated_at`

- **`evidence_packets`**
  - `id` (PK)
  - `session_id` (FK → `sessions.id`, unique)
  - `rubric_id` (FK → `rubrics.id`)
  - `packet_json` (JSONB; output of `integration/evidence_packet/pipeline.py`)
  - `created_at`, `updated_at`

- **`session_reviews`**
  - `id` (PK)
  - `session_id` (FK → `sessions.id`)
  - `reviewer_id` (FK → `users.id`)
  - `final_scores` (JSONB; per-criterion teacher scores if differing from packet)
  - `comments` (text)
  - `flags` (JSONB; e.g., `needs_retake: true`)
  - `created_at`, `updated_at`

For media artifacts (`recording.mp4`, `final_transcript.json`, screenshots):

- MVP: store them on disk (NFS / shared volume) or S3-like object storage.
- Store only the URIs / paths in the `sessions.artifacts` JSONB column.

---

## 4. Central Backend: FastAPI Layout

Create a new package, e.g. `backend/`, with:

- `backend/main.py`
  - Creates FastAPI app.
  - Registers routers for `rubrics`, `question_sets`, `assessments`, `sessions`, `reviews`.
  - Configures DB connection (SQLAlchemy + Postgres URL from env).

- `backend/models.py`
  - SQLAlchemy/SQLModel table definitions for the entities above.

- `backend/schemas.py`
  - Pydantic models mapping to API request/response shapes:
    - `RubricCreate`, `RubricRead`
    - `QuestionSetCreate`, `QuestionSetRead`
    - `AssessmentCreate`, `AssessmentRead`
    - `SessionCreate`, `SessionRead`
    - `EvidencePacketRead`
    - `SessionReviewCreate`, `SessionReviewRead`

- `backend/routes/`:
  - `rubrics.py`: implements `POST /rubrics` and `GET /rubrics/{id}`.
  - `question_sets.py`: implements `POST /question_sets` and `GET /question_sets/{id}`.
  - `assessments.py`: implements:
    - `POST /assessments`
    - `POST /assessments/{id}/publish`
    - `GET /assessments/{id}`
    - `GET /assessments/{id}/sessions`
  - `sessions.py`: implements:
    - `POST /sessions` (Jetson-facing)
    - `GET /sessions/{id}`
    - `GET /sessions/{id}/feedback`
    - `POST /sessions/{id}/artifacts`
    - `POST /sessions/{id}/evidence_packet` (optional, for on-device generation)
  - `reviews.py`: implements:
    - `POST /sessions/{id}/review`

- `backend/config.py`
  - Reads env vars: `DATABASE_URL`, `EVIDENCE_PACKET_STORAGE_ROOT`, `JETSON_ARTIFACTS_ROOT`, `OPENAI_API_KEY`, etc.

- `backend/evidence_jobs.py`
  - Thin wrapper around `integration/build_session_from_oral_exam.py` and `integration/evidence_packet/pipeline.py`.
  - Exposes a function `enqueue_evidence_job(session_id: str, rubric_id: str, artifacts: dict)` that:
    - Finds the relevant files on disk (from `artifacts` and configured roots).
    - Runs the normalization step.
    - Runs evidence-packet generation.
    - Writes `evidence_packet.json`.
    - Upserts into `evidence_packets` and updates `sessions` row.

Initially, `enqueue_evidence_job` can:

- Schedule a `BackgroundTasks` job inside FastAPI when `/sessions/{id}/artifacts` is called.
- Optionally log job state in `sessions.evidence_packet_status`.

---

## 5. Jetson-Local Backend Integration

On Jetson, add a small FastAPI app (e.g. under `jetson_runtime/jetson_backend/`):

- `jetson_runtime/jetson_backend/main.py`
  - FastAPI app with endpoints:
    - `POST /jetson/exams`
      - Input: `{ session_id, exam_config }` (or just `session_id` and look up exam config from local JSON).
      - Behavior:
        - Invoke `OralExamProctor` (from `proctor.py`) in a background thread/process.
        - Start tracking state in memory or a small local store (question text, status).
    - `GET /jetson/exams/{session_id}/state`
      - Reads current state from the running proctor.
      - Shape compatible with `ExamState` in `web/src/types/exam.ts` (status, questionText, transcriptPreview).
    - `POST /jetson/exams/{session_id}/stop`
      - Signals the proctor to stop early.

- Central backend integration from Jetson:
  - When a student begins an exam:
    - Jetson backend:
      - Calls central `POST /sessions` with `assessment_id` + optional `student_id`.
      - Receives `session_id`.
      - Starts `OralExamProctor` with that `session_id` so that artifacts land in `jetson_runtime/sessions/<session_id>/`.
  - When the exam finishes:
    - Jetson backend:
      - Knows the `session_id` and the local session directory.
      - Calls central `POST /sessions/{id}/artifacts` with URIs/paths like:
        - `recording_uri`: `jetson://sessions/<session_id>/recording.mp4` or a shared-storage path.
        - `final_transcript_uri`: `jetson://sessions/<session_id>/final_transcript.json`.
        - `session_dir_uri`: `jetson://sessions/<session_id>/`.

This aligns directly with the Jetson-facing endpoints described in `SYSTEM-DESIGN.md`.

---

## 6. Evidence Packet Pipeline Integration

Use the existing `integration/` code without modification where possible:

- From the central backend (`backend/evidence_jobs.py`):
  - Given a `session_id` and `rubric_id`:
    1. Construct the local paths:
       - `session_dir` (from config and `sessions.artifacts`).
       - `rubric_path` (from `rubrics.rubric_json` or a saved JSON file).
    2. Run normalization:
       - Call `build_session_from_oral_exam.py` programmatically (import and call its main function) or via its CLI to produce a normalized session JSON (like `evidence_packet_session_1.json.session.json`).
    3. Run evidence-packet pipeline:
       - Import `integration.evidence_packet.pipeline.run_evidence_packet`.
       - Pass `rubric_path`, `session_path`, `out_path`, and an `llm_complete` wrapper that uses the configured OpenAI client.
    4. Persist:
       - Read the resulting `evidence_packet.json`.
       - Store it into `evidence_packets.packet_json`.
       - Update `sessions.evidence_packet_status = 'ready'`, `score_total`, `score_max`.

The teacher UI can then:

- Call `GET /sessions/{id}` to retrieve:
  - Session metadata.
  - Evidence packet JSON (or a summarized view).
  - Artifact URIs (recording, transcript, screenshots).

---

## 7. Web App Integration Points

Update the React app in `web/` to call real APIs instead of mocks:

- **Student flow (`web/src/api/studentExam.ts`):**
  - Replace `mockStudentExamApi` with a real `StudentExamApi` implementation:
    - `createSession(input)`:
      - Calls Jetson-local `POST /sessions` (or `POST /jetson/exams` which internally calls central `/sessions`).
      - Returns `{ sessionId }` from the response.
    - `getExamState(sessionId)`:
      - Calls Jetson-local `GET /jetson/exams/{sessionId}/state`.
      - Maps the response into `ExamState`.
    - `endExam(sessionId)`:
      - Calls Jetson-local `POST /jetson/exams/{sessionId}/stop`.

- **Teacher flow:**
  - Add API modules similar to `studentExam.ts` for:
    - `GET /assessments` and `GET /assessments/{id}`.
    - `GET /assessments/{id}/sessions`.
    - `GET /sessions/{id}` for review pages.
    - `POST /sessions/{id}/review` for the override flow.
  - Wire the existing teacher pages (`/teacher/review`, `/teacher/done`, etc.) to:
    - Load an example assessment and session from the real backend.
    - Submit teacher overrides via `POST /sessions/{id}/review`.

Backend base URLs:

- In `web/`, define environment variables:
  - `VITE_CENTRAL_API_BASE_URL` (e.g., `https://api.socrates.example.com`).
  - `VITE_JETSON_API_BASE_URL` (e.g., `http://localhost:8000` on Jetson).
  - API modules read from these env vars.

---

## 8. Incremental Implementation Phases

To keep risk low, implement in phases:

1. **Phase 1: Central backend skeleton**
   - Set up `backend/` FastAPI app with:
     - Health check endpoint.
     - Postgres connection.
     - Minimal models: `rubrics`, `assessments`, `sessions`.
   - Implement:
     - `POST /rubrics`, `POST /assessments`, `POST /sessions`.
     - `GET /assessments/{id}`, `GET /assessments/{id}/sessions`.
   - Keep evidence packet generation and Jetson integration mocked.

2. **Phase 2: Hook up React teacher UI**
   - Create real teacher API clients in `web/src/api/`.
   - Replace hardcoded mocks on teacher pages with backend data.
   - Use a single example assessment + sessions seeded into the DB.

3. **Phase 3: Jetson-local backend**
   - Implement `jetson_runtime/jetson_backend/` with:
     - `POST /jetson/exams`, `GET /jetson/exams/{session_id}/state`, `POST /jetson/exams/{session_id}/stop`.
   - Integrate with `OralExamProctor` and `session_manager.py`.
   - For now, let Jetson backend only manage local exam state; don’t yet call central backend.

4. **Phase 4: Central–Jetson session wiring**
   - On exam start:
     - Jetson backend calls central `POST /sessions` and uses returned `session_id` for `jetson_runtime` session directory naming.
   - On exam end:
     - Jetson backend calls central `POST /sessions/{id}/artifacts` with paths/URIs.

5. **Phase 5: Evidence packet jobs**
   - Implement `backend/evidence_jobs.py`.
   - On `/sessions/{id}/artifacts`, enqueue background job to:
     - Run `build_session_from_oral_exam` and `run_evidence_packet`.
     - Persist `evidence_packets` and update `sessions` fields.
   - Expose `GET /sessions/{id}` returning evidence packet summary for teacher UI.

6. **Phase 6: Student feedback + polish**
   - Implement `GET /sessions/{id}/feedback` and surface it in a simple student-facing “results” page.
   - Add auth/permissions (teacher vs student), better error handling, logging, and observability.

---

## 9. Configuration & Deployment Notes

- **Configuration strategy:**
  - Use environment variables or a `backend/settings.py` module with:
    - `DATABASE_URL`
    - `EVIDENCE_PACKET_STORAGE_ROOT`
    - `JETSON_SESSIONS_ROOT` (matching `jetson_runtime/config/settings.py`)
    - `OPENAI_API_KEY`
    - `CENTRAL_API_BASE_URL` (for Jetson backend)

- **Deployment:**
  - Central backend:
    - Containerize FastAPI app with Uvicorn.
    - Deploy alongside a managed Postgres instance.
  - Jetson backend:
    - Run FastAPI app as a systemd service or Docker container on Jetson.
    - Ensure it has access to `jetson_runtime/` code and `/mnt/ssd/oral_exam_sessions/`.

This plan should provide a clear path from the current mocked/demo state to a functioning backend and database that respects the contracts in `SYSTEM-DESIGN.md` and reuses the core logic already implemented in `jetson_runtime/` and `integration/`.

---

## 10. Bridging From Mocks to Real Data (Concrete Tasks)

The codebase currently has:

- A working Jetson exam pipeline (`jetson_runtime` + `jetson_backend.py`).
- A working evidence-packet pipeline (`integration/`).
- A React app that still uses **mock data** for most central-backend concepts (assessments, sessions, evidence packets).

To move to **end-to-end real data**, implement these three pieces in order.

### 10.1 Jetson → Central Backend Wiring

Goal: when a real oral exam runs on Jetson, a corresponding `sessions` row and its artifacts exist in the central DB.

**Tasks**

1. **Teach Jetson backend where the central API lives**
   - In `jetson_runtime/jetson_backend.py` (or `config` for it), add:
     - `CENTRAL_API_BASE_URL` env-driven setting (e.g. `https://api.socrates.example.com`).
   - Add a small HTTP helper using `httpx` or `requests`:
     - `post_json(path: str, payload: dict) -> dict`.

2. **On exam start, create a central session**
   - In `create_exam` (or equivalent handler for `POST /jetson/exams`):
     - Before starting `OralExamProctor`, call central:
       - `POST {CENTRAL_API_BASE_URL}/sessions` with body:
         - `assessment_id`
         - `student_id` (if known; nullable for MVP)
         - Optional `device_info` (Jetson id, hostname).
     - Use the returned `session_id` as:
       - The Jetson `session_id` stored in `_ExamRuntime`.
       - The directory name for `jetson_runtime/sessions/<session_id>/`.
     - Store `central_session_id` in `_ExamRuntime` as well (same as local `session_id` for MVP).

3. **On exam end, notify central about artifacts**
   - In `_run_exam` after `proctor.conduct_exam()` completes and the proctor shuts down:
     - Construct a payload with artifact URIs/paths, e.g.:
       - `recording_uri`: `jetson://sessions/<session_id>/recording.mp4`
       - `final_transcript_uri`: `jetson://sessions/<session_id>/final_transcript.json`
       - `session_dir_uri`: `jetson://sessions/<session_id>/`
     - Call:
       - `POST {CENTRAL_API_BASE_URL}/sessions/{session_id}/artifacts` with `{ artifacts: {...} }`.
   - Central backend should:
     - Mark `sessions.status` = `evidence_pending`.
     - Enqueue the evidence job (see §6 and §10.2).

### 10.2 Central Backend Read/Write APIs for Teacher UI

Goal: provide all the data the teacher frontend needs, backed by the DB + evidence pipeline.

**Endpoints to implement (if not already done)**

1. **Assessments list for “View Past Exams”**
   - `GET /assessments`
   - Response shape (example):
     ```json
     [
       {
         "id": "bayes-oral-v1",
         "title": "Bayes' Rule Oral Exam",
         "total_sessions": 12,
         "unreviewed_sessions": 3
       },
       ...
     ]
     ```
   - Implementation:
     - Join `assessments` with `sessions`.
     - Derive counts per assessment.

2. **Assessment detail for grade distribution + sessions table**
   - `GET /assessments/{id}/sessions`
   - Response:
     - `assessment` summary (title, description).
     - `sessions`: array of session summaries:
       ```json
       {
         "id": "sess-001",
         "student_name": "Student A",
         "date_iso": "2026-03-01T10:00:00Z",
         "status": "pending|ready|reviewed",
         "score": 5.5
       }
       ```
     - Optional `grade_buckets`: aggregated counts by grade band (A/B/C/D), derived from `evidence_packets.packet_json.total_score / max_score`.

3. **Session detail for evidence + review view**
   - `GET /sessions/{id}`
   - Response shape:
     - `session` metadata: `assessment_id`, `student_id`, `started_at`, `ended_at`, `status`.
     - `evidence_packet`: either full JSON or a summarized form (per-criterion scores, quotes, flags).
     - `artifacts`: URIs for transcript, recording, etc.
     - `review` (if exists): previously submitted teacher review data.
   - Implementation:
     - Join `sessions`, `evidence_packets`, and `session_reviews`.

4. **Teacher review submission**
   - `POST /sessions/{id}/review`
   - Body:
     - `final_scores` (optional per-criterion overrides).
     - `comments` (free text).
     - Optional flags (`needs_retake`, etc.).
   - Behavior:
     - Insert or update a `session_reviews` row.
     - Mark `sessions.status = 'reviewed'`.

5. **Student feedback (optional for later)**
   - `GET /sessions/{id}/feedback`
   - Response:
     - A filtered view of evidence/teacher review suitable for students (e.g. overall score, high-level comments).

### 10.3 Frontend: Replace Mocks with Real API Calls

Goal: switch the React app from mock data to the real backend while preserving the UX already built.

**Student UI**

1. **Switch from `mockStudentExamApi` to `StudentExamApi` that calls Jetson backend**
   - In `web/src/api/studentExam.ts`:
     - Keep the shape of `StudentExamApi` but implement:
       - `createSession(input)`:
         - Either:
           - Call central `POST /sessions` and then `POST /jetson/exams`, or
           - Call Jetson `POST /jetson/exams` which internally creates the central session (preferred).
       - `getExamState(sessionId)`:
         - Call `GET {VITE_JETSON_API_BASE_URL}/jetson/exams/{sessionId}/state`.
       - `doneSpeaking(sessionId)`:
         - Call `POST {VITE_JETSON_API_BASE_URL}/jetson/exams/{sessionId}/done`.
       - `endExam(sessionId)`:
         - Call `POST {VITE_JETSON_API_BASE_URL}/jetson/exams/{sessionId}/stop`.
   - Update `StudentPrepPage` and `StudentSessionPage` to import the real implementation instead of the mock.

**Teacher UI**

2. **Create a `teacherApi` module**
   - `web/src/api/teacher.ts` (for example) using `VITE_CENTRAL_API_BASE_URL`:
     - `getAssessments()` → `GET /assessments`.
     - `getAssessmentSessions(assessmentId)` → `GET /assessments/{id}/sessions`.
     - `getSession(sessionId)` → `GET /sessions/{id}`.
     - `submitSessionReview(sessionId, payload)` → `POST /sessions/{id}/review`.

3. **Wire teacher pages to the real API**
   - `TeacherAssessmentsPage`:
     - Replace `mockAssessments` with `await teacherApi.getAssessments()`.
   - `TeacherAssessmentDetailPage`:
     - Replace `mockGradeBucketsByAssessment` and `mockSessions` with:
       - Data from `getAssessmentSessions(assessmentId)` (including derived grade buckets).
   - `TeacherSessionDetailPage` and/or `TeacherReviewPage`:
     - Replace `teacherReviewData` with `await teacherApi.getSession(sessionId)`:
       - Use its evidence packet summary and existing review (if any).
     - Wire “Mark review complete” / override controls to `submitSessionReview`.

4. **Environment configuration**
   - Ensure `VITE_CENTRAL_API_BASE_URL` and `VITE_JETSON_API_BASE_URL` are set correctly for:
     - Local dev (might be `http://localhost:8002` for central and `http://localhost:8001` for Jetson emulator).
     - Jetson deployment (Jetson app uses local base URL; teacher UI uses remote central base URL).

With these three blocks implemented (10.1–10.3), running a real exam on Jetson will:

1. Create a central `sessions` row.
2. Attach artifacts on completion and trigger evidence-packet generation.
3. Allow the teacher UI to list real assessments and sessions, open a session, and see the true evidence packet and review controls instead of mock placeholders.


