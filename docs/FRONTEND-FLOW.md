## Frontend Flow — Teacher and Student UIs

This document describes the current web frontend flows, routes, and how they connect to the Jetson backend and central APIs. It reflects the MVP implementation in `web/`.

---

## 1. Student UI Flow (Jetson-hosted)

### 1.1 Routes and pages

- **`/` → `LandingPage`**
  - **Role**: Neutral role chooser.
  - **Behavior**:
    - Shows two entry buttons:
      - `I'm a student` → `/student`
      - `I'm a teacher` → `/teacher`

- **`/student` → `StudentHomePage`**
  - **Role**: Student main hub.
  - **Behavior**:
    - Shows student welcome text and two actions:
      - `Start an Exam` → `/student/assessments`
      - `Pre-prep Practice` → `/student/study/prep`

- **`/student/assessments` → `StudentAssessmentsPage`**
  - **Role**: Exam selector page.
  - **Behavior**:
    - Calls `teacherApi.getAssessments()` to fetch assessments from:
      - The **central backend** (`GET /assessments`) when `VITE_CENTRAL_API_BASE_URL` is set, or
      - Local **mock data** when it is not set.
    - Renders a table with:
      - Assessment title.
      - Total sessions.
      - Unreviewed sessions.
    - Each row has a **“Start Exam”** link to:
      - `/student/prep?assessmentId=<id>`.

- **`/student/study/prep` → `StudentStudyPrepPage`**
  - **Role**: Study-mode intro page.
  - **Behavior**:
    - Shows how study mode works and camera/photo guidance.
    - `Begin Study` navigates to `/student/study/config` (preserving `assessmentId` query when present).

- **`/student/study/config` → `StudentStudyConfigPage`**
  - **Role**: Study-mode configuration page.
  - **Behavior**:
    - Lets students choose:
      - Course (when central question bank is available).
      - Topic.
      - Number of questions.
    - `Start Practice` creates the study run and navigates to:
      - `/student/study/session?sessionId=<id>&assessmentId=<id>`.

- **`/student/prep` → `StudentPrepPage`**
  - **Role**: Greeting + General Instructions.
  - **Behavior**:
    - Builds a time-of-day greeting for the student (`buildTimeOfDayGreeting`).
    - Reads `assessmentId` from the query string (falls back to a demo id if absent).
    - Uses `teacherApi.getAssessments()` to resolve and display the chosen assessment title (when available).
    - Shows preparation guidance (“quiet place”, “camera pointed at your face”) and what to expect (follow-ups, evidence packet).
    - **Begin exam** button:
      - Calls `studentExamApi.createSession({ assessmentId })`, which:
        - Issues `POST {VITE_JETSON_API_BASE_URL}/jetson/exams` with a generated `session_id`.
      - On success, navigates to `/student/session?sessionId=<id>`.

- **`/student/session` → `StudentSessionPage`**
  - **Role**: Live exam “Questions” view for the student.
  - **Major pieces**:
    - **Question/status panel (left, top)**:
      - Uses `sessionId` from the URL query.
      - On mount, starts polling:
        - `GET {VITE_JETSON_API_BASE_URL}/jetson/exams/{sessionId}/state` every few seconds via `studentExamApi.getExamState(sessionId)`.
      - Displays:
        - Session id.
        - Status pill: `Listening` / `Speaking` / `Thinking` / `Complete` (mapped from `ExamState.status`).
        - Question body text (`ExamState.questionText`).
    - **Transcript preview (left, middle)**:
      - Shows a running text preview (`ExamState.transcriptPreview`) if present.
      - Otherwise shows a placeholder message.
    - **Footer controls (left, bottom)**:
      - **“I’m done” button**:
        - Calls `studentExamApi.doneSpeaking(sessionId)` which hits:
          - `POST {VITE_JETSON_API_BASE_URL}/jetson/exams/{sessionId}/done`
        - This triggers `OralExamProctor.request_done()` on Jetson, causing the current `listen_for_response()` loop to end early—equivalent to the terminal Enter key in the CLI flow.
      - **“End exam (prototype)” link**:
        - Navigates to `/student/done`.
        - Does not yet send an explicit “stop” signal to the backend; in a full implementation this would call `POST /jetson/exams/{sessionId}/stop` (already available) and/or a central `/sessions/{id}/complete`.
    - **Camera panel (right)**:
      - Handles browser camera permissions and preview:
        - `Enable camera` → uses `getUserMedia({ video: { facingMode: 'user' }, audio: false })`.
        - Renders the live video stream into a `<video>` element.
        - `Stop camera` stops all tracks and clears the video source.
      - This is **purely a preview** inside the browser; the real exam video is recorded by the Jetson camera stack, not this media stream.

- **`/student/done` → `StudentDonePage`**
  - **Role**: Exam ends page.
  - **Behavior**:
    - Confirms that the exam is complete in this prototype.
    - In the full system, this page would show a confirmation that the assessment is recorded and may optionally include a very high-level “thanks, your instructor will review” message.

### 1.2 APIs used by the student UI (today)

All through `web/src/api/studentExam.ts`:

- `POST {VITE_JETSON_API_BASE_URL}/jetson/exams` → create a new proctor session on Jetson.
- `GET {VITE_JETSON_API_BASE_URL}/jetson/exams/{sessionId}/state` → fetch exam state (status, question, transcript preview).
- `POST {VITE_JETSON_API_BASE_URL}/jetson/exams/{sessionId}/done` → signal that the student is done speaking (per question).
- `POST {VITE_JETSON_API_BASE_URL}/jetson/exams/{sessionId}/stop` → stop/abort the exam (currently only wired in the API client, not used by UI buttons yet).

---

## 2. Teacher UI Flow (Web-based)

The teacher UI flow is currently **mock-backed** (no live DB), but mirrors the desired UX:

- Global entry point: `/` role chooser page.
- Teacher home entry: `/teacher`.
- Teacher-centric routes live under `/teacher/...`.

### 2.1 Home page (teacher console)

- **`/teacher` → `HomePage`**
  - Centered header and two primary actions:
    - **View Past Exams**:
      - Route: `ROUTE_PATH.TEACHER_ASSESSMENTS` → `/teacher/assessments`.
    - **Create New Exams**:
      - Route: `ROUTE_PATH.TEACHER_CREATE_EXAM` → `/teacher/assessments/new`.
  - This page conceptually replaces the earlier “Published assessments + upload card” layout with a cleaner two-button hub.

- **Legacy compatibility route**
  - `/home` redirects to `/teacher`.

### 2.2 View Past Exams: Assessments list

- **`/teacher/assessments` → `TeacherAssessmentsPage`**
  - Uses `teacherApi.getAssessments()` to load assessments from:
    - `GET {VITE_CENTRAL_API_BASE_URL}/assessments` (when configured), or
    - Local mocks (`mockAssessments`) when no backend is present.
  - Renders a table:
    - **Assessment**: title (e.g. “Bayes' Rule Oral Exam”).
    - **Total sessions**: number of sessions for this assessment.
    - **Unreviewed sessions**: number of sessions not yet reviewed.
    - **Actions**: “View” link per row.
  - Each “View” link navigates to:
    - `/teacher/assessments/{assessmentId}` (`TeacherAssessmentDetailPage`).
  - In real deployments, this is backed by the central backend’s `GET /assessments`.

### 2.3 Assessment detail: Grade distribution + sessions table

- **`/teacher/assessments/:assessmentId` → `TeacherAssessmentDetailPage`**
  - Header:
    - Breadcrumb: `Past exams / <assessment title>`.
    - Title: assessment name.
    - Subtitle: status + number of sessions (from backend/mocks).
  - **Grade distribution bar chart**:
    - Uses `grade_buckets` from `teacherApi.getAssessmentSessions(assessmentId)`:
      - In real mode, populated from the central backend’s computed grade buckets for the assessment.
      - In mock mode, uses `mockGradeBucketsByAssessment`.
  - **Sessions table**:
    - Data from `sessions` in the `AssessmentSessionsResponse`.
    - Columns:
      - **Student**: name or identifier.
      - **Date**: human-readable time from `dateIso`.
      - **Status**: `pending` | `ready` | `reviewed` (mapped to colors).
      - **Score**:
        - If `status === 'pending'` → “Pending”.
        - If `score` present → numeric (e.g. `6.0`).
        - Else → “—”.
      - **Actions**: “Open” link.
    - Each “Open” link navigates to:
      - `/teacher/sessions/{sessionId}` (`TeacherSessionDetailPage`).
    - In real mode, this data comes from `GET /assessments/{id}/sessions`.

### 2.4 Session detail: Evidence packet view + review controls

- **`/teacher/sessions/:sessionId` → `TeacherSessionDetailPage`**
  - Uses `teacherApi.getSession(sessionId)`:
    - Real mode: `GET /sessions/{id}` from the central backend.
    - Mock mode: synthesizes a `SessionDetail` based on `mockSessions` and `teacherReviewData`.
  - Header:
    - Breadcrumb: `Past exams / <assessmentId> / <studentName>`.
    - Title: “Session for <student>”.
  - Evidence packet summary:
    - In real mode, reads from the evidence packet JSON (or summary) returned by the backend.
    - In mock mode, uses `teacherReviewData` as a placeholder.
  - Review section:
    - Explains where per-criterion controls will live.
    - Contains a **“Mark review complete”** button that currently leads to `TeacherDonePage` (prototype).
    - In a full integration, this will call `POST /sessions/{id}/review`.

### 2.5 Create New Exams: Form → JSON + optional backend create (MVP)

- **`/teacher/assessments/new` → `TeacherCreateExamPage`**
  - Form sections:
    - **Assessment basics**:
      - Title field.
      - Questions textarea (one question per line).
    - **Rubric criteria**:
      - Editable list of `(id, name, max)` rows.
      - “+ Add criterion” button to append a new row.
  - Derived outputs:
    - **Rubric JSON**:
      - Matches the `rubric` schema used by `integration/evidence_packet` (rubric_id, scale, criteria with `id`, `name`, `description`, `max`, `anchors`, `weight`).
    - **Exam config JSON**:
      - `exam_id`, `title`, `system_prompt`, `questions[*]` containing `id`, `text`, `rubric_items`, `max_follow_ups`.
    - Both are rendered in `<pre>` blocks for copy-paste.
  - Submission behavior:
    - “Create assessment (if backend configured)” button calls `teacherApi.createAssessment(...)`.
      - Real mode: posts to `POST /rubrics` and `POST /assessments` on the central backend and shows the created `assessmentId`.
      - Mock mode: keeps working as a JSON generator and shows a message that the backend is not configured.

---

## 3. Relationship to Backend & Jetson

At MVP stage, the frontend flow is **backend-aware with safe mock fallbacks**:

- Student UI always talks directly to the Jetson backend (`/jetson/exams`, `/jetson/exams/{id}/state`, `/done`, `/stop`) using `VITE_JETSON_API_BASE_URL`.
- Teacher and student assessment listing UIs go through `teacherApi`, which:
  - Uses the central backend (`VITE_CENTRAL_API_BASE_URL`) when available.
  - Falls back to local mocks when it is not, so the UI remains usable for demos without a running backend.

This lets us test UI flows and Jetson integration immediately, while progressively turning on real central backend endpoints without breaking the React app.

For **question-bank study mode** (planned course/topic flows), see [`QUESTION-BANK-STUDY-MODE-INTEGRATION.md`](./QUESTION-BANK-STUDY-MODE-INTEGRATION.md) **§0.2** for how that work relates to `VITE_CENTRAL_API_BASE_URL` and local central in dev.

