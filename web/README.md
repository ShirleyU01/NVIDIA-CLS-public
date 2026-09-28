# Socrates Web MVP (Teacher & Student UIs)

This `web/` package contains a small React + TypeScript + Vite app that prototypes the **teacher** and **student** flows described in `docs/SYSTEM-DESIGN.md`.

The goal is to visualize:

- How teachers review **evidence packets** and override grades.
- How students experience the **oral exam selection → prep → session → done** flow.

Teacher data can come from a **real central backend** (when `VITE_CENTRAL_API_BASE_URL` is set) or from **mock data** if the backend is not running. Student exam state always comes from the **Jetson backend** (`jetson_runtime/jetson_backend.py`) via `VITE_JETSON_API_BASE_URL`.

---

## What’s implemented

### Teacher-facing pages

- **Home** (`/`)
  - “Teacher console” with two main actions:
    - **View Past Exams** → `/teacher/assessments`.
    - **Create New Exams** → `/teacher/assessments/new`.

- **Past exams list** (`/teacher/assessments`)
  - Uses `teacherApi.getAssessments()`:
    - In real mode: `GET {VITE_CENTRAL_API_BASE_URL}/assessments`.
    - In mock mode: `mockAssessments`.
  - Shows a table of assessments (title, total sessions, unreviewed sessions) with “View” links.

- **Assessment detail** (`/teacher/assessments/:assessmentId`)
  - Uses `teacherApi.getAssessmentSessions(assessmentId)`:
    - Real mode: `GET /assessments/{id}/sessions`.
    - Mock mode: `mockSessions` + `mockGradeBucketsByAssessment`.
  - Renders a grade-distribution bar chart and a sessions table (student, date, status, score).

- **Session detail** (`/teacher/sessions/:sessionId`)
  - Uses `teacherApi.getSession(sessionId)`:
    - Real mode: `GET /sessions/{id}` (session summary + evidence packet + review).
    - Mock mode: synthesizes a placeholder summary from `teacherReviewData`.
  - Shows an evidence packet summary and a “Mark review complete” prototype action.

- **Create new exam (MVP)** (`/teacher/assessments/new`)
  - Form that:
    - Collects assessment title and questions.
    - Collects basic rubric criteria (id, name, max).
    - Renders **rubric JSON** and **exam config JSON** for copy-paste.
  - “Create assessment (if backend configured)” button:
    - Real mode: posts rubric and assessment to the central backend via `teacherApi.createAssessment`.
    - Mock mode: leaves data local and shows a message that no backend is configured.

### Student-facing pages

- **Assessments list** (`/student/assessments`)
  - Uses `teacherApi.getAssessments()` to show available exams (title, total, unreviewed).
  - “Take exam” links route to `/student/prep?assessmentId=<id>`.

- **Prep / instructions** (`/student/prep`)
  - Greeting for the student.
  - Resolves the current assessment **title** via `teacherApi.getAssessments()` (when available).
  - “Before you begin” and “What to expect” bullet lists.
  - **Begin exam** button:
    - Calls `studentExamApi.createSession({ assessmentId })` (in `src/api/studentExam.ts`).
    - Under the hood this hits `POST {VITE_JETSON_API_BASE_URL}/jetson/exams`.
    - Navigates to `/student/session?sessionId=...`.

- **Exam session** (`/student/session`)
  - Reads `sessionId` from the query string.
  - Polls `studentExamApi.getExamState(sessionId)` every few seconds:
    - `GET {VITE_JETSON_API_BASE_URL}/jetson/exams/{sessionId}/state`.
  - Updates:
    - Question text.
    - Status pill (“Listening / Speaking / Thinking / Complete / Connecting”).
    - Transcript preview text.
  - Camera preview using `getUserMedia` for a live video feed.
  - **“I’m done”** button:
    - Calls `studentExamApi.doneSpeaking(sessionId)` → `POST /jetson/exams/{id}/done`.
  - “End exam (prototype)” link to the done page.

- **Exam done** (`/student/done`)
  - Confirms that the exam is complete and that the instructor will review later.

---

## Tech stack

- React 19 + TypeScript
- Vite with `@vitejs/plugin-react`
- React Router v7 for routing
- CSS Modules for page-level styling, plus global design tokens in `src/index.css`

Entry points:

- `index.html` – HTML shell.
- `src/main.tsx` – mounts `App` into `#root` with `BrowserRouter`.
- `src/App.tsx` – defines the route tree.

---

## How to run (for local testing)

From the **repo root**:

```bash
cd web
npm install        # first time
npm run dev
```

Then open:

- `http://localhost:5173/`

You can directly hit any route, for example:

- Teacher assessments: `http://localhost:5173/teacher/assessments`
- Student assessments: `http://localhost:5173/student/assessments`

### Testing the student flow

1. Go to `http://localhost:5173/student/assessments`.
2. Click **“Take exam”** next to an available exam, which routes to `/student/prep?assessmentId=...`.
2. Click **“Begin exam”**:
   - The UI calls `studentExamApi.createSession`, which hits the Jetson backend.
   - You are navigated to `/student/session?sessionId=...`.
3. On `/student/session`:
   - The page polls `getExamState` on the Jetson backend and updates question + transcript preview.
   - You can enable the camera preview to simulate the Jetson camera panel.
4. Click **“End exam (prototype)”** to go to the done page.

---

## Build (prototype)

```bash
cd web
npm run build
```

This type-checks with TypeScript and creates a static build under `dist/` for experimentation or future deployment.

