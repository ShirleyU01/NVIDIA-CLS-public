## Socrates Oral Exam, Study Mode & Evidence Packet

**Open the app:** [https://shirleyu01.github.io/NVIDIA-CLS-public/app/](https://shirleyu01.github.io/NVIDIA-CLS-public/app/) — the product UI, with sample exams, so it can be opened from this repo without a Jetson. Teacher login: `teacher` / `dropouts210`. Speech, camera, and live study sessions run on the device; the source for that runtime is `jetson_runtime/`.

**Case study:** [A spoken exam that can show its work](https://shirleyu01.github.io/NVIDIA-CLS-public/) — the shareable overview of what this system is, how the Jetson exam and the evidence check fit together, and where to read the code.

Built by Alfred Yu, Shirley Yu, Aya Aburous, and Jad Bitar in Stanford CS210A/B, in collaboration with NVIDIA. Piloted in Stanford CS109 with 50+ students across 89 sessions, 600+ questions, and 150+ chat interactions. The project won NVIDIA’s award at the end of the quarter.

This repo contains the core pieces of the **Socrates** system for running spoken exams and AI-guided study sessions on Jetson devices, normalizing the resulting artifacts, generating verifiable LLM-backed evidence packets, and surfacing student usage metrics for teachers.

**Quick links:** [Code structure](#code-structure-overview) · [Setup instructions](#setup-instructions) · [Question bank pipeline](#question-bank-pipeline) · [Full-stack quick start](#full-stack-quick-start-real-apis--db) · [Study Mode](#running-study-mode) · [Central backend API](#central-backend-fastapi) · [Testing](#testing)

---

## Code structure (overview)

```
NVIDIA-CLS-1/
├── backend/                    # Central FastAPI backend (rubrics, assessments, sessions)
│   ├── main.py                 # FastAPI app, CORS, /healthz
│   ├── config.py               # Settings (DB URL, session roots, API keys)
│   ├── database.py             # SQLAlchemy engine, Base, SessionLocal
│   ├── models.py               # SQLAlchemy models (Rubric, Assessment, Session, EvidencePacket)
│   ├── schemas.py              # Pydantic request/response schemas
│   ├── evidence_jobs.py        # Runs session normalization + evidence pipeline, persists results
│   └── routes/                 # API routers
│       ├── __init__.py         # api_router (mounts all routes)
│       ├── rubrics.py          # POST/GET rubrics
│       ├── question_sets.py    # Question set CRUD
│       ├── assessments.py      # GET assessments, sessions
│       ├── sessions.py         # POST sessions, artifacts, review; GET session detail
│       ├── students.py         # Lightweight student registration and survey status
│       ├── question_bank.py    # Course/topic discovery, selection, seen-question history
│       └── study_dashboard.py  # Study Mode metrics summary for teachers
│
├── jetson_runtime/             # Jetson oral exam + study-mode runtime
│   ├── run_exam.py             # CLI: run oral exam from exam JSON
│   ├── proctor.py              # OralExamProctor — orchestrates questions, STT/TTS, vision
│   ├── jetson_backend.py       # FastAPI app: /jetson/exams, state, done, stop
│   ├── session_manager.py      # Session lifecycle and artifact paths
│   ├── config/settings.py      # STT model, OpenAI, sessions dir, etc.
│   ├── stt/                    # Speech-to-text
│   │   ├── stt_service.py      # STTService
│   │   └── audio_capture.py    # Audio capture for STT
│   ├── tts/                    # Text-to-speech (e.g. Piper on Jetson)
│   │   └── tts_client.py
│   ├── vlm/                    # Vision / camera
│   │   └── camera.py
│   ├── cloud_llm/              # Cloud LLM client (OpenAI) for proctor
│   ├── study_guide/            # Study-mode paper capture, AMA, and feedback helpers
│   ├── exams/                  # Example exam JSON configs
│   ├── sessions/<id>/          # Per-session outputs: recordings, transcripts, paper captures, feedback
│   ├── metrics/                # Study Mode metrics mirror used by the teacher dashboard
│   └── tests/
│
├── integration/                # Evidence packet pipeline (session → graded packet)
│   ├── build_session_from_oral_exam.py   # Normalize jetson_runtime session dir → session JSON
│   ├── run_evidence_packet_from_oral_exam.py  # CLI: session dir + rubric → evidence_packet.json
│   ├── evidence_packet/        # Core pipeline
│   │   ├── pipeline.py         # load_rubric, load_session, run_evidence_packet, assemble_final_packet
│   │   ├── models.py           # QABlock, Screenshot
│   │   ├── prompts.py          # build_system_prompt, build_user_prompt
│   │   ├── validation.py       # validate_packet_item
│   │   ├── llm.py              # llm_complete() stub (override for your LLM)
│   │   └── llm_openai.py       # OpenAI implementation of llm_complete
│   ├── fixtures/               # Sample rubrics and mock session JSONs
│   └── tests/                  # Tests for session build + evidence packet
│
├── question_bank/              # PDF → topic retrieval → generated question bank pipeline
│   ├── pipeline.py             # Orchestrates ingest, chunk, embed, retrieve, generate, evaluate, export
│   ├── paths.py                # Resolves QUESTION_BANK_DATA_ROOT and default data root
│   ├── configs/                # Course topics and default oral rubric
│   └── tests/
│
├── web/                        # Teacher + student web app (React + Vite)
│   ├── src/
│   │   ├── App.tsx             # Router and layout
│   │   ├── main.tsx
│   │   ├── api/                # API clients
│   │   │   ├── studentExam.ts  # Jetson backend (VITE_JETSON_API_BASE_URL)
│   │   │   └── teacher.ts      # Central backend (VITE_CENTRAL_API_BASE_URL)
│   │   ├── pages/              # Student & teacher pages
│   │   │   ├── HomePage.tsx
│   │   │   ├── StudentAssessmentsPage, StudentPrepPage, StudentSessionPage, StudentDonePage
│   │   │   ├── StudentStudyPrep/Id/Config/Session/Review/Survey pages
│   │   │   ├── TeacherAssessmentsPage, TeacherAssessmentDetailPage, TeacherSessionDetailPage
│   │   │   ├── TeacherStudyDashboardPage
│   │   │   ├── TeacherCreateExamPage, TeacherReviewPage, TeacherFeedbackPage, ...
│   │   ├── data/               # Mock data (mockAssessments, teacherReview)
│   │   ├── types/              # assessment, exam, teacherReview
│   │   ├── routes/paths.ts
│   │   └── utils/
│   ├── package.json
│   └── vite.config.ts
│
├── docs/                       # Design and flow docs
│   ├── SYSTEM-DESIGN.md
│   ├── EVIDENCE-PACKET-PIPELINE-PLAN.md
│   ├── FRONTEND-FLOW.md
│   ├── STUDY-MODE-PRODUCT-BRIEF.md
│   ├── STUDY-MODE-DASHBOARD-PLAN.md
│   └── BACKEND-INTEGRATION-PLAN.md
│
├── question_bank_data/         # Default generated/checkpointed question-bank artifacts
├── question_bank_test_data/    # Isolated CS109 pipeline test data
├── scripts/                    # Developer smoke tests and utility scripts
├── requirements.txt            # Top-level Python deps (backend + integration)
├── evidence_packets/           # Default output for normalized session JSON + evidence packets (backend)
└── evidence_packet.json        # Example output (root; can be moved)
```

### What each part does

| Part | Role |
|------|------|
| **`backend/`** | Central API: store rubrics, question sets, assessments, student rows, session metadata, question-bank selection state, and study dashboard summaries. Uses SQLite by default (`DATABASE_URL`). |
| **`jetson_runtime/`** | Jetson-side oral exam and study-mode runtime: runs the proctor (STT/TTS/vision), writes session artifacts under `sessions/<id>/`, mirrors dashboard metrics under `metrics/`, and exposes Jetson APIs through `jetson_backend.py`. |
| **`integration/`** | Evidence pipeline: turns a session folder + rubric into a normalized session JSON and then into a graded `evidence_packet.json` (LLM-backed). Used by the backend evidence job and by the CLI `run_evidence_packet_from_oral_exam.py`. |
| **`question_bank/`** | Course-material pipeline: ingests PDFs, chunks and embeds source material, retrieves topic context, generates/evaluates questions, and exports proctor-ready exam JSON. |
| **`question_bank_data/`** | Default artifact root for question-bank checkpoints and exports. Override with `QUESTION_BANK_DATA_ROOT` for isolated runs. |
| **`web/`** | Single React app: oral exam flow, Study Mode flow, teacher assessment/review pages, and teacher Study Mode dashboard. Uses real central/Jetson APIs when base URLs are set, with limited mock/demo fallbacks for local dev. |

For detailed contracts and flows, see `docs/SYSTEM-DESIGN.md`, `docs/EVIDENCE-PACKET-PIPELINE-PLAN.md`, and `docs/FRONTEND-FLOW.md`.

---

## High-Level System Overview

At a high level, the system connects four layers:

- **Teacher workflow (backend + teacher UI)**
  - Teachers upload **rubrics** and **question sets** (PDF or JSON).
  - These are parsed into structured JSON and combined into **assessments**.
  - Teachers later review **sessions** and their generated **evidence packets**.

- **Student workflows (Jetson + student UI)**
  - In oral exam mode, students take a spoken exam while Jetson records audio/video, transcripts, screenshots, and related artifacts.
  - In Study Mode, students pick a course/topic, solve questions on paper, capture their work with the camera, get immediate AI feedback, use an AMA tutor chat, and receive an end-of-session summary.
  - Jetson writes raw session artifacts under `jetson_runtime/sessions/` and mirrors dashboard-ready telemetry under `jetson_runtime/metrics/`.

- **Evidence packet pipeline (backend or Jetson)**
  - Takes a **rubric JSON** and a **normalized session JSON**.
  - Calls an LLM (or mock) to score each rubric criterion, with structured reasoning.
  - Produces a machine-readable **evidence packet** that can be stored and visualized.

- **APIs (conceptual)**
  - Teacher endpoints: manage rubrics, question sets, assessments, sessions, and reviews.
  - Student endpoints: register student IDs, fetch survey state, select question-bank practice, and fetch eventual feedback.
  - Jetson endpoints: create oral/study sessions, evaluate paper/oral answers, register artifacts, and optionally upload a ready-made evidence packet.
  - Dashboard endpoints: summarize Study Mode metrics from the Jetson metrics mirror.

For the detailed contract and endpoint sketches, see `docs/SYSTEM-DESIGN.md`.

---

## Repo layout (quick reference)

- **`jetson_runtime/`** — Jetson oral exam and Study Mode runtime: `proctor.py`, `stt/`, `tts/`, `vlm/`, `study_guide/`, `config/settings.py`, `jetson_backend.py`; session outputs under `sessions/<session_id>/` and dashboard metrics under `metrics/`.
- **`integration/`** — Evidence packet pipeline: `build_session_from_oral_exam.py`, `run_evidence_packet_from_oral_exam.py`, `evidence_packet/` (pipeline, models, prompts, validation, LLM adapters), `fixtures/`, `tests/`.
- **`backend/`** — Central backend: `main.py`, `models.py`, `database.py`, `schemas.py`, `evidence_jobs.py`, `routes/` (rubrics, question_sets, assessments, sessions, students, question_bank, study_dashboard).
- **`question_bank/`** — Question-bank generation and export pipeline; default artifacts live in `question_bank_data/`.
- **`web/`** — Teacher + student React app: `src/pages/`, `src/api/`, `src/data/` (mocks); oral exam and Study Mode student flows use Jetson + central APIs, while teacher flows use central APIs.
- **`docs/`** — `SYSTEM-DESIGN.md`, `EVIDENCE-PACKET-PIPELINE-PLAN.md`, `FRONTEND-FLOW.md`, `BACKEND-INTEGRATION-PLAN.md`, `STUDY-MODE-PRODUCT-BRIEF.md`, and `STUDY-MODE-DASHBOARD-PLAN.md`.

The **code structure** section above has the full tree and a short description of each part.

---

## Setup instructions

### Prerequisites

- **Python 3.10+** (for backend, integration, and jetson_runtime)
- **Node.js 18+** and **npm** (for `web/`)
- **Optional:** `OPENAI_API_KEY` for LLM-backed evidence packets and for jetson_runtime proctor cloud LLM

### 1. Python environment

From repo root:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt
pip install -r jetson_runtime/requirements.txt   # for oral exam + Jetson backend
pip install -r question_bank/requirements.txt    # for question-bank generation
```

**Environment variables** (optional, depending on what you run):

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | Evidence packet LLM and jetson_runtime proctor cloud LLM |
| `OPENAI_BASE_URL` | Optional. Use a different API endpoint (e.g. proxy or OpenAI-compatible API) for lower latency. |
| `OPENAI_LLM_MODEL` / `EVIDENCE_PACKET_MODEL` | Model name (default: `gpt-5.4-mini`). Use a faster model for low latency. |
| `DATABASE_URL` | Central backend DB (default: `sqlite:///./socrates_backend.db`) |
| `JETSON_SESSIONS_ROOT` | Where session folders live (default: `jetson_runtime/sessions`) |
| `EVIDENCE_PACKET_STORAGE_ROOT` | Where normalized session + evidence JSONs are written (default: `evidence_packets/`) |
| `QUESTION_BANK_DATA_ROOT` | Optional question-bank artifact root (default: `question_bank_data/`) |
| `CENTRAL_API_BASE_URL` | Used by Jetson backend to notify central backend when an exam finishes |
| `VITE_CENTRAL_API_BASE_URL` | Used by the web app to call the central backend (default local dev: `http://localhost:8002`) |
| `VITE_JETSON_API_BASE_URL` | Used by the web app to call the Jetson backend (default local dev: `http://localhost:8001`) |

Jetson-specific audio/video config: see `jetson_runtime/config/settings.py`.

### 2. Web app (teacher + student UI)

From repo root:

```bash
cd web
npm install
```

To run the dev server (after starting backend(s) as below):

```bash
export VITE_JETSON_API_BASE_URL="http://localhost:8001"   # optional; for student exam API
export VITE_CENTRAL_API_BASE_URL="http://localhost:8002"  # optional; for teacher API (else mocks)
npm run dev
```

Then open **http://localhost:5173**. Student flow uses Jetson; teacher flow uses central backend or mocks.

### 3. Study mode launcher

For local demos on a machine that can open GUI terminals, `RUN_STUDY_MODE.py` starts the central backend, Jetson backend, and web UI together:

```bash
source .venv/bin/activate
python RUN_STUDY_MODE.py
```

The script reads `.env` if present and uses `jetson_runtime/jetson_backend.py` for the Jetson service.

---

## Question Bank Pipeline

The `question_bank/` package turns course materials into validated practice/oral-exam questions. By default it writes checkpoints and exports under `question_bank_data/`; set `QUESTION_BANK_DATA_ROOT` to use an isolated folder such as `question_bank_test_data/`.

```bash
source .venv/bin/activate
pip install -r question_bank/requirements.txt

# Run through retrieval/checkpoint stages for CS109.
python -m question_bank.pipeline --course CS109

# Run the full generation/export path. Requires OPENAI_API_KEY.
python -m question_bank.pipeline --course CS109 --through export
```

Typical artifacts:

- `question_bank_data/parsed/` — parsed source documents.
- `question_bank_data/chunks/` and `question_bank_data/embeddings/` — retrieval inputs and indices.
- `question_bank_data/final_question_bank/<COURSE>/` — validated topic files, `merged_bank.json`, and `export_exam.json`.

For the full design and stage-by-stage contract, see `docs/QUESTION-BANK-PIPELINE.md`.

---

## Running an Oral Exam on Jetson (Local Dev)

From repo root:

```bash
source .venv/bin/activate
cd jetson_runtime
python run_exam.py --exam exams/example_exam.json
```

This:

- Launches the oral exam proctor (STT/TTS/vision loop).
- Writes all artifacts under `jetson_runtime/sessions/<exam_id-or-session_N>/`, including:
  - `transcript.json`, `final_transcript.json`
  - `recording.mp4`
  - `images/`, `mini_transcripts/`, and text/markdown transcripts.

These artifacts are the inputs to the *session normalization* and evidence packet pipeline.

---

## Generating an Evidence Packet from a Real Session (CLI)

With an existing session folder under `jetson_runtime/sessions/<session_id>/` and a rubric JSON (e.g. `integration/fixtures/rubric_bayes_oral_v1.json`), run:

```bash
PYTHONPATH=. python -m integration.run_evidence_packet_from_oral_exam \
  --session-dir jetson_runtime/sessions/session_1 \
  --rubric integration/fixtures/rubric_bayes_oral_v1.json \
  --out evidence_packet_session_1.json
```

### Running with a mock LLM (no external API calls)

To smoke-test the full end-to-end flow without `OPENAI_API_KEY`:

```bash
PYTHONPATH=. python -m integration.run_evidence_packet_from_oral_exam \
  --session-dir jetson_runtime/sessions/session_1 \
  --rubric integration/fixtures/rubric_bayes_oral_v1.json \
  --out evidence_packet_session_1.json \
  --llm mock
```

The output will be:

- A **normalized session JSON** (optional, controlled by flags).
- An **evidence packet JSON** at the path given by `--out`.

---

## Central Backend (FastAPI)

For development, the central backend uses a simple SQLite DB by default (configurable via `DATABASE_URL`).

From repo root:

```bash
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8002
```

This starts a FastAPI app with:

- `GET /healthz` — health check.
- `POST /rubrics`, `GET /rubrics/{id}` — store rubric JSON blobs.
- `GET /assessments` — list assessments (with total/unreviewed session counts).
- `GET /assessments/{id}`, `GET /assessments/{id}/sessions` — assessment detail + sessions table.
- `POST /sessions` — create a session row (used by Jetson or other clients).
- `POST /sessions/{id}/artifacts` — register Jetson artifacts and enqueue an evidence job.
- `GET /sessions/{id}` — session detail including evidence packet JSON and any teacher review.
- `POST /sessions/{id}/review` — persist teacher overrides/comments.
- `POST /students/ensure` — create a lightweight student row for Study Mode sign-in.
- `GET /question-bank/courses`, `GET /question-bank/courses/{course}/topics`, `POST /question-bank/courses/{course}/selection` — discover and select file-backed question-bank practice.
- `GET /study-dashboard/summary` — read Study Mode metrics from `jetson_runtime/metrics/` and return teacher-dashboard rollups.

`backend/evidence_jobs.py` calls `integration/build_session_from_oral_exam.py` and `integration/evidence_packet/pipeline.py` under the hood, so evidence generation is the same whether you invoke it via CLI or via this backend.

For the full backend design, see `docs/BACKEND-INTEGRATION-PLAN.md`.

---

## Full-Stack Quick Start (Real APIs + DB)

This sequence starts **central backend**, **Jetson backend**, and the **web app** with real HTTP calls. Mock fallbacks are used only when a base URL is not configured.

**Prerequisite:** complete [Setup instructions](#setup-instructions) above (venv, `pip install`, `npm install` in `web/`).

### 1. Start the central backend

From repo root:

```bash
source .venv/bin/activate

# Optional: use Postgres instead of SQLite
# export DATABASE_URL="postgresql+psycopg2://user:pass@localhost:5432/socrates"

uvicorn backend.main:app --reload --port 8002
```

Serves teacher/session APIs at **http://localhost:8002** (health: `GET /healthz`). For the full endpoint list, see [Central Backend (FastAPI)](#central-backend-fastapi).


### 2. Start the Jetson backend (or emulate locally)

In a new terminal, from repo root:

```bash
source .venv/bin/activate
cd jetson_runtime

export CENTRAL_API_BASE_URL="http://localhost:8002"
python jetson_backend.py
```

This exposes `http://localhost:8001` with:

- `POST /jetson/exams`
- `GET /jetson/exams/{session_id}/state`
- `POST /jetson/exams/{session_id}/done`
- `POST /jetson/exams/{session_id}/stop`
- Study Mode endpoints under `/jetson/study-guide/...` for creating runs, capturing paper/oral answers, evaluating work, tutor chat, survey submission, and ending a run.

When an exam finishes, it will also call `POST {CENTRAL_API_BASE_URL}/sessions/{session_id}/artifacts` with artifact paths under `jetson_runtime/sessions/<session_id>/`.

### 3. Start the web app

In another terminal, from repo root:

```bash
cd web
npm install          # first time only

export VITE_JETSON_API_BASE_URL="http://localhost:8001"
export VITE_CENTRAL_API_BASE_URL="http://localhost:8002"

npm run dev
```

Then open `http://localhost:5173` in your browser.

- **Student:** go to `/student/assessments` → pick an exam → `/student/prep?assessmentId=...` → **Begin exam** → `/student/session?sessionId=...` → `/student/done`.
- **Study Mode:** go to `/student/study/prep` → `/student/study/id?assessmentId=...` → `/student/study/config` → `/student/study/session?sessionId=...` → review/survey/done.
- **Teacher:** go to `/teacher/assessments` → pick an assessment → `/teacher/assessments/:id` → open a session `/teacher/sessions/:sessionId` or create a new exam at `/teacher/assessments/new`.
- **Study dashboard:** go to `/teacher/study-dashboard`; it reads local metrics from `jetson_runtime/metrics/` through `GET /study-dashboard/summary`.

With the environment variables set as above, these flows use **real HTTP calls** to the Jetson backend and central backend. If `VITE_CENTRAL_API_BASE_URL` is omitted, the teacher/student assessment pages fall back to local mock data but the student exam still talks to the real Jetson backend.

---

## Running Study Mode

Study Mode is the paper-practice flow. It uses both the central backend and the Jetson backend:

1. The central backend stores student/session metadata, serves the question-bank selection API, and exposes the dashboard summary.
2. The Jetson backend stores paper captures, immediate feedback, end-of-session feedback, survey artifacts, and dashboard metrics.
3. The web app coordinates the student and teacher flows.

### 1. Start the central backend

From repo root:

```bash
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8002
```

### 2. Start the Jetson backend

In a new terminal:

```bash
source .venv/bin/activate
cd jetson_runtime
CENTRAL_API_BASE_URL="http://localhost:8002" python jetson_backend.py
```

By default this starts FastAPI on `http://0.0.0.0:8001`. For Study Mode, it writes:

- Raw session artifacts under `jetson_runtime/sessions/<session_id>/`.
- Dashboard metrics under `jetson_runtime/metrics/students/<student_id>/day_runs/<day_run_id>/sessions/<session_id>/`.

### 3. Start the web app

In another terminal:

```bash
cd web
npm install   # first time only
VITE_CENTRAL_API_BASE_URL="http://localhost:8002" \
VITE_JETSON_API_BASE_URL="http://localhost:8001" \
npm run dev
```

Then open `http://localhost:5173`.

The Study Mode flow is:

- **Prep:** `/student/study/prep`
- **Student ID:** `/student/study/id?assessmentId=<id>`
- **Configuration:** `/student/study/config?assessmentId=<id>&studentId=<student_id>`
- **Active session:** `/student/study/session?sessionId=<id>`
- **Review:** `/student/study/review/<sessionId>`
- **Survey:** `/student/study/survey/<sessionId>`

The teacher dashboard is available at `/teacher/study-dashboard` and reads the metrics mirror through the central backend. Metrics are local runtime artifacts; to analyze Jetson data on another machine, copy or commit `jetson_runtime/metrics/` to the same relative path before starting the central backend.

---

## Running the Student Oral Exam Web App (Jetson or Local Dev)

The original oral exam flow still uses the Jetson backend (`jetson_runtime/jetson_backend.py`) and the assessment pages in `web/`.

### 1. Start the Jetson backend

From repo root:

```bash
source .venv/bin/activate
cd jetson_runtime
python jetson_backend.py
```

### 2. Start the web app

```bash
cd web
VITE_JETSON_API_BASE_URL="http://localhost:8001" npm run dev
```

The student flow is:

- **Assessments list**: `http://localhost:5173/student/assessments`
  - Shows available exams (from the central backend via `teacherApi` when configured, or mocks).
  - “Take exam” routes to the prep page for that assessment.
- **Greeting + instructions**: `http://localhost:5173/student/prep?assessmentId=<id>`
  - Shows exam-specific title and instructions.
  - “Begin exam” calls `POST /jetson/exams` (via `studentExamApi.createSession`) and navigates to the session page.
- **Questions page**: `http://localhost:5173/student/session?sessionId=<id>`
  - Polls `GET /jetson/exams/{id}/state` to show the current question and status.
  - Provides an **“I’m done”** button that calls `POST /jetson/exams/{id}/done`, which causes the Jetson proctor to stop listening for the current answer and move on.
  - Offers an “End exam (prototype)” link to the done page.
- **Exam complete**: `http://localhost:5173/student/done`
  - Simple confirmation screen (in a full system this would be tied to backend session completion).

For detailed page-by-page behavior, see `docs/FRONTEND-FLOW.md` (Student UI section).

---

## Running the Teacher Web App

The teacher UI uses the central backend when `VITE_CENTRAL_API_BASE_URL` is configured. Some pages retain mock/demo fallbacks when the central URL is absent.

With the same `npm run dev` command as above, open:

- **Teacher home**: `http://localhost:5173/`
  - Two primary actions:
    - **View Past Exams** → `/teacher/assessments`
    - **Create New Exams** → `/teacher/assessments/new`

- **View Past Exams**: `/teacher/assessments`
  - Uses `teacherApi.getAssessments()`:
    - Real mode: `GET {VITE_CENTRAL_API_BASE_URL}/assessments`.
    - Mock mode: `mockAssessments`.

- **Assessment detail**: `/teacher/assessments/:assessmentId`
  - Uses `teacherApi.getAssessmentSessions(assessmentId)`:
    - Real mode: `GET /assessments/{id}/sessions`.
    - Mock mode: `mockSessions` + `mockGradeBucketsByAssessment`.

- **Session detail**: `/teacher/sessions/:sessionId`
  - Uses `teacherApi.getSession(sessionId)`:
    - Real mode: `GET /sessions/{id}`.
    - Mock mode: synthesised summary from `teacherReviewData`.

- **Create New Exams**: `/teacher/assessments/new`
  - Form-to-JSON UX, plus:
    - A **“Create assessment (if backend configured)”** button that calls `teacherApi.createAssessment`.
    - In real mode this posts to the central backend; in mock mode it simply reports that only local JSON was generated.

- **Study dashboard**: `/teacher/study-dashboard`
  - Uses `GET {VITE_CENTRAL_API_BASE_URL}/study-dashboard/summary`.
  - Reads `jetson_runtime/metrics/` on the machine running the central backend.
  - Shows sessions, students, activation, completion, survey rates, timing, oral/paper answer counts, and topic-level rollups.

Again, `docs/FRONTEND-FLOW.md` has a more exhaustive description of these flows.

---

## Testing

Run the full test suite:

```bash
pytest -q
```

Or focus on integration / adapter tests, e.g.:

```bash
pytest -q integration/test_build_session_from_oral_exam.py
pytest -q integration/test_evidence_packet.py
```

These tests exercise:

- Session normalization from `jetson_runtime` artifacts.
- Evidence packet pipeline behavior (both real and mock LLMs).

---

## Credits

We would like to acknowledge the CS 210 teaching staff for their help in facilitating this, and NVIDIA for providing the Jetson Orin Nano that was used.

**Study mode** (camera preview, browser capture upload, Jetson study-guide API, and related frontend): **Aya** and **Jad**.

Recent study-guide work by **Aya** and **Jad** includes:

- **Ask me anything (AMA)** — floating tutor chat on the study session page, backed by the Jetson `action=ama` API. The tutor prompt includes the full practice run (all questions and rubrics), the current capture feedback, prior graded `paper/q*/paper_feedback.md` notes from disk, and the growing AMA thread so context stays current across questions.
- **Feedback as math** — in-session feedback (and AMA replies) rendered with Markdown + KaTeX (`$...$` / `$$...$$`) instead of plain preformatted text.
- **Study config UX** — question count is a normal numeric field (type freely, 1–20) without awkward spinner-only behavior, and zero is rejected as a count.
- **Clearer feedback typography** — slightly larger type on the live study feedback panel and the post-session study review page for readability.
- **Captured photo preview reset** — when the student advances to the next question, the Jetson backend clears `last_image_url` / `last_image_path` so the UI no longer shows the previous question’s thumbnail until a new capture exists.
- **Mobile AMA polish** — composer controls use at least 16px text and `touch-action: manipulation` so iOS Safari does not zoom the viewport when opening or focusing the AMA panel.

Post-session feedback for student and instructor + changes across frontend to make tone warmer: **Alfred**

Question bank generation pipeline, including RAG of relevant midterm documents: **Shirley** 

---

## Additional Documentation

- **System architecture**: see `docs/SYSTEM-DESIGN.md`.
- **Evidence packet internals**: see `docs/EVIDENCE-PACKET-PIPELINE-PLAN.md`.
- **Post-session study feedback**: see `docs/STUDY-FEEDBACK-PIPELINE.md`.
- **Oral exam pipeline**: see `jetson_runtime/PIPELINE.md`.
- Optional course wiki: `https://github.com/cs210/NVIDIA-CLS-1/wiki`
