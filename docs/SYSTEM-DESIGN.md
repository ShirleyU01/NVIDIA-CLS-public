## System Design Overview

This document captures the high-level design for:

- **Backend API** (teacher, student, Jetson endpoints)
- **Frontends** (teacher UI and student UI)
- **Jetson exam pipeline** (oral examiner runtime)
- **Evidence packet pipeline** and how it plugs into the rest of the system

For detailed evidence-packet internals, see `EVIDENCE-PACKET-PIPELINE-PLAN.md`.

---

## Backend Design

### Core resources

- **Rubric**
  - Defines scoring criteria and anchors.
  - Stored as JSON in a DB column or blob storage (structure matches `integration/fixtures/rubric_bayes_oral_v1.json` and §5 of `EVIDENCE-PACKET-PIPELINE-PLAN.md`).

- **Question set / materials**
  - Teacher-authored content for an assessment:
    - Questions text.
    - Any additional instructions or supporting materials (PDFs, images, etc.).
  - For MVP, questions and rubric are uploaded as **PDFs** and converted into our internal JSON shape by a simple parsing script (can be upgraded to LLM-based parsing later).

- **Assessment**
  - A published exam definition that students can take.
  - Links together:
    - A rubric.
    - A question set / materials bundle.
    - Metadata (title, subject, status, created_by, etc.).

- **Session**
  - A single student’s attempt on a specific assessment.
  - Has:
    - `assessment_id`
    - `student_id` (or anonymous id)
    - Runtime metadata (start/end time, device info).
    - Pointers to **artifacts** produced by the Jetson oral-exam runtime (recordings, transcripts, etc.).

- **Evidence packet**
  - Machine-generated grading artifact for a **(rubric, session)** pair.
  - JSON structure as in `EVIDENCE-PACKET-PIPELINE-PLAN.md` (§7).
  - Stored in the DB, associated with a session (and implicitly its assessment).

### REST API (MVP)

All endpoints are conceptual; concrete URL prefixes and auth are left flexible.

#### Teacher-facing endpoints

- **`POST /rubrics`**
  - Body: rubric JSON or uploaded rubric PDF (MVP: JSON directly; PDF via a helper service).
  - Behavior: create a new rubric, return `rubric_id`.

- **`POST /question_sets`**
  - Body: question-set JSON or PDF (MVP: PDF only is acceptable; parsed server-side into JSON).
  - Behavior: create a question set, return `question_set_id`.

- **`POST /materials`**
  - Optional additional assets (PDFs, images, etc.).
  - Behavior: upload attachments and return URIs; used when building an assessment.

- **`POST /assessments`**
  - Body: references existing rubric + question set + metadata.
  - Behavior: create draft assessment; not visible to students yet.

- **`POST /assessments/{id}/publish`**
  - Body: optional publish settings (start/end date, visibility).
  - Behavior: mark assessment as **published**, making it discoverable by students.

- **`GET /assessments/{id}/sessions`**
  - Behavior: list all sessions for this assessment.
  - Response: array of `{session_id, student_id, started_at, status, evidence_packet_status}`.

- **`GET /sessions/{id}`**
  - Behavior: return all information needed for teacher review:
    - Session metadata.
    - Links/URIs to artifacts (recording, transcript).
    - The evidence packet JSON (or a summary).

- **`POST /sessions/{id}/review`**
  - Behavior: persist human review:
    - Final teacher score(s) + comments.
    - Any overrides of the evidence packet’s scores.
    - Flags (e.g. “needs re-take”).

#### Student-facing endpoints

- **`GET /assessments/{id}`** (student view)
  - Behavior: return:
    - Student-safe assessment metadata (title, description).
    - Instructions.
    - Question set in the format needed by the student UI.
  - Used to render:
    - Greeting page.
    - General instructions.
    - Questions flow.

- **`GET /sessions/{id}/feedback`**
  - Behavior: return what a student can see **after** review:
    - Final score(s).
    - Optional feedback text or high-level evidence packet summary.

#### Jetson-facing endpoints

Jetson runs the oral examiner runtime and calls backend APIs to synchronize session metadata and artifacts.

- **`POST /sessions`**
  - Behavior: create a new session for an assessment.
  - Input:
    - `assessment_id`
    - `student_id` (if known)
  - Response:
    - `session_id`
    - Optionally, configuration for the oral exam (system prompt, STT/TTS config overrides).

- **`POST /sessions/{id}/artifacts`**
  - Behavior: register that Jetson has produced artifacts for a session.
  - Input:
    - URIs or relative paths to:
      - `recording.mp4`
      - `transcript.json`
      - `final_transcript.json`
      - Screenshot directory (`images/`)
    - Alternatively, accept file uploads and store them server-side.
  - Side effect:
    - Triggers (or enqueues) evidence packet generation as a background job.

- **`POST /sessions/{id}/evidence_packet`** (optional; for on-device generation)
  - Behavior: Jetson sends a ready-made evidence packet JSON.
  - Server:
    - Validates and stores it.
    - Marks the session’s evidence-packet status as “ready”.

---

## Frontend Design

### Student UI (Jetson-hosted)

The student UI is a web app running on Jetson, talking to a local backend that wraps the `jetson_runtime` oral exam pipeline.

- **Screens**
  - **Greeting Page**
    - Shows exam name, short description.
    - “Start” button:
      - Calls `POST /sessions` (via Jetson backend) to create a session.
      - Navigates to General Instructions.
  - **General Instruction Page**
    - Shows exam rules, duration, expectations.
    - Simple mic/camera status indicators (Jetson backend can expose a health endpoint).
    - “Begin exam” button:
      - Signals Jetson backend to start the oral exam for this session (e.g. `POST /jetson/exams/{session_id}/start`).
      - Transitions to Questions Page.
  - **Questions Page**
    - Displays:
      - Current question text.
      - Optional rubric hints, if desired.
      - Status indicator: `Listening` / `Speaking` / `Thinking` / `Complete`.
    - UI Polls or subscribes (e.g. WebSocket) to the Jetson proctor service for:
      - Current question index.
      - Whether the system is speaking (TTS), listening (STT), or generating follow-ups.
      - When exam is complete.
     - Provides an **“I’m done”** control:
       - When clicked, calls a Jetson endpoint (`POST /jetson/exams/{session_id}/done`) which sets a flag in `OralExamProctor` to stop listening for the current answer, mirroring the terminal “press Enter when done” behavior.
  - **Exam Ends Page**
    - “Your exam is complete” message.
    - May optionally say: “Your instructor will review your results and provide feedback later.”

### Teacher UI (web-based)

The teacher UI is a web app that talks to the central backend.

- **Entry**
  - Home (`/`) is a **role chooser** (student vs teacher).
  - Teacher home is `/teacher`, which shows the teacher console with:
    - **View Past Exams** → assessments list.
    - **Create New Exams** → exam creation form.
  - Student home is `/student`, which branches into:
    - Exam mode (`/student/assessments`).
    - Pre-prep practice (`/student/study/prep`).

- **Past exams flow**
  - **Assessments list** (`/teacher/assessments`):
    - Table of assessments with:
      - Title.
      - Total sessions.
      - Unreviewed sessions.
    - Clicking an assessment navigates to its detail view.
  - **Assessment detail** (`/teacher/assessments/{assessment_id}`):
    - Header summarizing the assessment and counts.
    - **Grade distribution** visualization (e.g. bar chart of A/B/C/D counts) driven by evidence-packet scores.
    - **Sessions table**:
      - Columns: student, date, status, score (numeric or “Pending” if evidence is not ready).
      - Clicking a session opens its detail view.
  - **Session detail** (`/teacher/sessions/{session_id}`):
    - Evidence packet view:
      - Per-criterion scores, anchors, quotes, and flags.
    - Transcript / recording links.
    - **Teacher review controls**:
      - Final score / overrides.
      - Free-text comments.
      - Submits via `POST /sessions/{id}/review`.

- **Create new exam flow (MVP)**
  - **Create exam form** (`/teacher/assessments/new`):
    - Lets an instructor define:
      - Assessment title and questions (one per line).
      - Rubric criteria (id, name, max, basic anchors).
    - Generates:
      - Rubric JSON matching the evidence-packet schema.
      - Exam config JSON for the oral examiner (question texts + rubric_items).
    - In future iterations this form can be extended to:
      - Accept rubric/question PDFs and call a parsing service.
      - Persist directly via `POST /rubrics`, `POST /question_sets`, `POST /assessments`, and `POST /assessments/{id}/publish`.

For a more detailed walkthrough of the current pages/routes, see `FRONTEND-FLOW.md`.

---

## Jetson Pipeline (Oral Exam Runtime)

The Jetson device runs the **oral examiner** using existing code in `jetson_runtime/`.

- **Core components**
  - `jetson_runtime/proctor.py` (`OralExamProctor`)
    - Orchestrates the exam:
      - Uses STT/TTS/vision to interact with the student.
      - Iterates through questions.
      - Generates follow-ups based on rubric items.
      - Writes session artifacts under `jetson_runtime/sessions/<session_id>/`.
  - `jetson_runtime/stt/`
    - `stt_service.py`: `STTService` using `faster_whisper` on Jetson.
    - `audio_capture.py`: wrappers around `arecord` + `ffmpeg`.
  - `jetson_runtime/tts/`
    - `tts_client.py`: `TTSClient` talking to a Piper TTS server on Jetson.
  - `jetson_runtime/vlm/`
    - `camera.py`: manages camera, continuous video recording, and screenshots.
  - `jetson_runtime/config/settings.py`
    - Central config for models, devices, audio/video params, and directories.

- **Session artifacts**
  - For each session (folder `jetson_runtime/sessions/<session_id>/`), the proctor writes:
    - `recording.mp4`
    - `transcript.json`
    - `final_transcript.json`
    - `final_transcript.md` / `transcript.txt`
    - `images/` (screenshots)
    - `mini_transcripts/` (LLM follow-up context)

- **Jetson web service (to be added)**
  - HTTP API or WebSocket on Jetson that wraps `OralExamProctor`, exposing:
    - `POST /jetson/exams`:
      - Input: `session_id`, exam configuration.
      - Behavior: starts an exam; proctor uses existing code.
    - `GET /jetson/exams/{session_id}/state`:
      - Behavior: returns current state for the student UI:
        - Question text.
        - Status (Speaking / Listening / Thinking).
        - Progress (current question index, total).
    - `POST /jetson/exams/{session_id}/done`:
       - Behavior: signals that the student is done speaking for the current response.
       - Implementation: calls `OralExamProctor.request_done()`, which causes the current `listen_for_response()` loop to terminate gracefully.
    - `POST /jetson/exams/{session_id}/stop`:
      - Behavior: abort exam early if needed.
  - When the session finishes, Jetson:
    - Calls central backend `POST /sessions/{id}/artifacts` with URIs for the files written above.

---

## Evidence Packet Design & Pipeline

The evidence packet pipeline is implemented under `integration/evidence_packet/` and documented in detail in `EVIDENCE-PACKET-PIPELINE-PLAN.md`. Here we summarize how it fits.

- **Inputs**
  - **Rubric JSON**:
    - Structure: `rubric_id`, `scale`, `criteria[*]` with `id`, `name`, `description`, `max`, `anchors`, `weight`.
  - **Session JSON** (normalized):
    - Structure: `session_id`, `recording_uri`, `qa_blocks[*]` with:
      - `block_id` (e.g. `"Q1"`).
      - `question` (text).
      - `student_answer` (full answer text for that block).
      - `screenshots[*]` with `timestamp`, `image_id`, `region`.

- **Session normalization from oral exam outputs**
  - Implemented in `integration/build_session_from_oral_exam.py`.
  - Reads:
    - `jetson_runtime/sessions/<session_id>/transcript.json`
    - `jetson_runtime/sessions/<session_id>/final_transcript.json`
  - Produces a normalized session JSON with:
    - `session_id` (from transcript or folder name).
    - `recording_uri` (session dir or `recording.mp4`, depending on config).
    - One QA block per question:
      - `question` from transcript.
      - `student_answer` as concatenation of:
        - All `responses[*].text`
        - All `follow_ups[*].response_text`
      - `screenshots` derived from `final_transcript.events`:
        - Each `screenshot` event is assigned to the most recent non-follow-up question.
        - `timestamp` = event `t`, `image_id` = event `path`, `region = null`.

- **Evidence packet generation**
  - Implemented in `integration/evidence_packet/pipeline.py`.
  - `run_evidence_packet(rubric_path, session_path, out_path, llm_complete_fn=None)`:
    1. Loads rubric + session.
    2. Normalizes session into typed `QABlock`s.
    3. For each criterion:
       - Builds a system + user prompt with rubric + QA blocks + a strict output schema.
       - Calls `llm_complete` (OpenAI or stub).
       - Parses JSON and validates via `validation.py`.
    4. Assembles a final packet with total/max scores, per-criterion items, and flags.
    5. Writes `evidence_packet.json` to `out_path`.

- **One-shot CLI from oral exam session**
  - Implemented in `integration/run_evidence_packet_from_oral_exam.py`:
    - `python -m integration.run_evidence_packet_from_oral_exam --session-dir jetson_runtime/sessions/session_1 --rubric integration/fixtures/rubric_bayes_oral_v1.json --out evidence_packet_session_1.json`
    - Steps:
      1. Build normalized session JSON from oral exam outputs.
      2. Optionally save it alongside the output.
      3. Run evidence-packet pipeline with either:
         - OpenAI-backed LLM (`--llm auto` with `OPENAI_API_KEY`), or
         - Mock LLM (`--llm mock`) for deterministic testing without external calls.

---

## End-to-End Integration Flow

### Authoring (teacher)

1. Teacher uses the **teacher UI** to:
   - Upload rubric PDF → parsed into rubric JSON → `POST /rubrics`.
   - Upload question set PDF → parsed into question-set JSON → `POST /question_sets`.
   - Create assessment → `POST /assessments`.
   - Publish assessment → `POST /assessments/{id}/publish`.

2. The assessment now appears in:
   - Teacher UI sidebar (published exams list).
   - Student UI’s list of available assessments for the relevant course/context.

### Delivery (student on Jetson)

1. Student opens student UI on Jetson:
   - UI fetches exam definition via `GET /assessments/{id}` (through a Jetson-friendly proxy/backend).

2. Student walks through:
   - Greeting Page → General Instruction Page.

3. When exam begins:
   - Backend (on Jetson) calls central `POST /sessions` to register a session.
   - Jetson proctor uses the configured exam data and runs the oral exam using `jetson_runtime/`.

4. When exam ends:
   - Jetson writes artifacts into `jetson_runtime/sessions/<session_id>/`.
   - Jetson calls `POST /sessions/{id}/artifacts` with paths/URIs.

### Evidence packet generation (background)

1. Backend receives artifact notification and enqueues a job:
   - Job reads session artifacts (directly from shared storage or from URIs).
   - Job runs:

   ```text
   build_session_from_oral_exam -> normalized session JSON
   run_evidence_packet -> evidence_packet.json
   ```

2. Backend persists the evidence packet JSON into the DB:
   - Updates session record: `evidence_packet_status = ready`, `score = total_score`, etc.

### Review (teacher)

1. Teacher opens teacher UI:
   - Sidebar: picks an assessment.
   - Main view: sees **all sessions** for that assessment.

2. Teacher clicks a session:
   - UI calls `GET /sessions/{id}`:
     - Shows evidence packet summary and flags.
     - Provides links to transcript / recording if deeper review is needed.

3. Teacher optionally records a review:
   - UI calls `POST /sessions/{id}/review` with final scores/comments.

4. If student feedback is enabled:
   - Student later calls `GET /sessions/{id}/feedback` and sees the relevant portion of the review and/or evidence packet.

---

This document is the high-level contract for how the existing Jetson pipeline (`jetson_runtime/*`) and the evidence packet pipeline (`integration/evidence_packet/*`) will be orchestrated via a backend API and surfaced through the teacher and student frontends. As we iterate, we can refine endpoint shapes, payloads, and authorization, but the core responsibilities and data flow should remain stable.

