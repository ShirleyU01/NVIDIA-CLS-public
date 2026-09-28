# jetson_runtime — AI Oral Examiner: Pipeline & Architecture

**Platform:** Jetson Orin Nano (8 GB RAM, 1 TB SSD at `/mnt/ssd`)  
**Attached hardware:** USB microphone, webcam (`/dev/video0`), speaker  
**Date:** Feb 2026

---

## 1. Design Goals

| Goal | Decision |
|------|----------|
| High-accuracy transcription | Run **faster-whisper `small.en`** locally (English-only model; ~460 MB RAM; dramatically better than `base`) |
| Natural speech synthesis | Run **Piper TTS** locally in Docker (`localhost:5000`) |
| Intelligent exam logic | **OpenAI GPT-4o-mini** via API (analysis, follow-up generation, final grading notes) |
| Student privacy | Audio, video, and screenshots **never leave the device**. Only text (transcripts) is sent to OpenAI |
| Evidence for grading | Per-session: timestamped final transcript, mini-transcripts, screenshots, `recording.mp4` |
| Storage | Session data → `/mnt/ssd/oral_exam_sessions/session_N/` (1 TB SSD) |

---

## 2. Hardware & Service Map

```
┌─────────────────────────── Jetson Orin Nano ─────────────────────────────┐
│                                                                            │
│  USB mic ──► arecord / faster-whisper (small.en)   [STT — runs locally]  │
│  Speaker ◄── Piper TTS Docker  :5000               [TTS — runs locally]  │
│  Webcam  ──► OpenCV camera capture                 [screenshots + video]  │
│                                                                            │
│  1TB SSD (/mnt/ssd)                                                        │
│    └── oral_exam_sessions/                                                 │
│         └── session_N/                                                     │
│              ├── recording.mp4          ← continuous video + audio        │
│              ├── final_transcript.json  ← timestamped full record         │
│              ├── final_transcript.md    ← human-readable version          │
│              ├── transcript.txt         ← plain stitched text             │
│              ├── mini_transcripts/                                         │
│              │    ├── mini_1.json       ← before follow-up 1              │
│              │    └── mini_2.json       ← before follow-up 2              │
│              └── images/                                                   │
│                   └── deixis_<ts>_<word>.jpg   ← trigger-word screenshots │
│                                                                            │
│  ┌────────────── Cloud API ──────────────────────────────────────────┐    │
│  │  OpenAI (GPT-4o-mini)                                             │    │
│  │   • Generate first question from rubric                           │    │
│  │   • Analyze student answer against rubric                         │    │
│  │   • Generate follow-up questions                                  │    │
│  │   • Produce final grading notes                                   │    │
│  │   Input: TEXT ONLY (transcript + rubric). No images, no audio.   │    │
│  └───────────────────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. STT: Why `small.en` Instead of `base`

| Model | Size (RAM) | WER (English) | Notes |
|-------|-----------|---------------|-------|
| `base` | ~140 MB | higher error rate | Used in V1 — frequently misses words |
| `small.en` | ~460 MB | **significantly lower** | English-only; already downloaded on device |
| `medium.en` | ~1.5 GB | best local accuracy | Possible upgrade if RAM allows |

**V2 uses `small.en`** (already cached at `~/.cache/huggingface/hub/`).  
Key transcription settings used:
- `beam_size=5` — balanced speed/accuracy (5 is standard for small)
- `vad_filter=True` — skip silence, don't waste compute
- `vad_parameters`: generous padding (600 ms each side) so first/last words aren't clipped
- `initial_prompt`: domain vocabulary hint (e.g. "oral exam, algorithm, Big-O, efficiency") — primes the model for technical language
- `language="en"` — explicit language lock avoids autodetect overhead

---

## 4. Teacher Setup (Exam Configuration)

The teacher provides **one JSON config file** per exam:

```json
{
  "exam_id": "cs101_midterm",
  "subject": "Algorithms — Big-O notation",
  "system_prompt": "You are an oral exam proctor for a university computer science course. The student is being assessed on their understanding of algorithmic complexity. You must ask one question at a time, wait for the student's response, and generate follow-up questions based on missing rubric items. Be encouraging but rigorous. Do not provide hints.",
  "questions": [
    {
      "text": "What is Big-O notation and why is it useful?",
      "rubric_items": [
        "Definition: describes growth rate / upper bound of runtime",
        "At least one concrete example (e.g. O(n), O(log n), O(n^2))",
        "Why it matters: compares algorithms, predicts scaling"
      ],
      "max_follow_ups": 2
    },
    {
      "text": "What is the difference between O(n log n) and O(n^2) for sorting?",
      "rubric_items": [
        "O(n log n) is faster for large inputs",
        "Example of O(n log n) sort: merge sort or heap sort",
        "Example of O(n^2) sort: bubble sort or insertion sort",
        "Practical implication: n^2 becomes unusable for large n"
      ],
      "max_follow_ups": 2
    }
  ]
}
```

---

## 5. Session Lifecycle

```
Teacher runs:
  python3 proctor.py --exam config/cs101_midterm.json

SESSION START
│
├─ Assign session ID: session_N  (auto-incrementing counter on SSD)
├─ Create /mnt/ssd/oral_exam_sessions/session_N/
├─ Start continuous video recording:  recording_raw.mp4  (5 fps, 480×270)
├─ Start parallel audio recording:    audio_temp.wav     (arecord)
│
│   FOR EACH QUESTION in exam config:
│   │
│   ├─ [1] GENERATE QUESTION
│   │       Send to OpenAI: system_prompt + rubric + "generate question N"
│   │       Receive: question text
│   │       TTS speaks the question
│   │
│   ├─ [2] LISTEN TO STUDENT ANSWER
│   │       Record in 1-second slices (keyboard Enter or "I'm done" stops early)
│   │       Max recording time: 60 seconds
│   │       Every 3 slices: transcribe with faster-whisper for trigger-word detection
│   │       On trigger word ("this", "that", "here", "diagram", etc.):
│   │           → Capture screenshot from camera → save to images/
│   │       After answer: final transcription of full audio (faster-whisper small.en)
│   │       Store: response dict {text, segments (with timestamps), vision_captures, duration}
│   │
│   ├─ [3] FOR EACH FOLLOW-UP (up to max_follow_ups):
│   │   │
│   │   ├─ Build mini-transcript:
│   │   │     Chronological events so far for this question:
│   │   │       {t: 0.0,  type: "question",    text: "..."}
│   │   │       {t: 1.2,  type: "answer",       text: "..."}   ← one entry per segment
│   │   │       {t: 4.5,  type: "screenshot",   path: "images/deixis_...", trigger_word: "this"}
│   │   │       ...
│   │   │     Save: mini_transcripts/mini_N.json
│   │   │
│   │   ├─ Send to OpenAI:
│   │   │     system_prompt + rubric + mini_transcript text events + "generate follow-up"
│   │   │     (screenshots are NEVER sent — only text)
│   │   │
│   │   ├─ TTS speaks the follow-up question
│   │   └─ Listen to student answer (same as step 2)
│   │
│   └─ [4] NEXT QUESTION
│
SESSION END
│
├─ Stop video recording → stop arecord → ffmpeg mux → recording.mp4
├─ Build FINAL TRANSCRIPT (chronological across all questions):
│     {t, type, text/path, question_number, follow_up}
│     Save: final_transcript.json + final_transcript.md
├─ Build plain transcript.txt (stitched text)
└─ Print summary
```

---

## 6. Mini-Transcript Format

Saved before each follow-up. Contains **everything said so far in this question round**, chronologically timestamped. Only sent as text to OpenAI (no images).

```json
{
  "question": "What is Big-O notation and why is it useful?",
  "rubric_items": ["Definition...", "Example...", "Why it matters..."],
  "events": [
    {"t": 0.0,  "type": "text",       "text": "Big-O notation is about how fast an algorithm grows"},
    {"t": 1.8,  "type": "text",       "text": "like O of n squared means it grows quadratically"},
    {"t": 4.2,  "type": "screenshot", "path": "images/deixis_1740000000_this.jpg", "trigger_word": "this"},
    {"t": 5.0,  "type": "text",       "text": "so this graph shows that"}
  ]
}
```

**Note:** Screenshots are saved to disk for evidence. The path is included in the JSON for reference (e.g. for human reviewers). OpenAI only receives the text events.

---

## 7. Final Transcript Format

Built at the end of the session. Contains the full chronological record across all questions, formatted for post-processing and grading.

### JSON (`final_transcript.json`)
```json
{
  "exam_id": "cs101_midterm",
  "session_id": "session_3",
  "start_time": "2026-02-25T10:03:12",
  "end_time":   "2026-02-25T10:21:45",
  "events": [
    {"t": 0.00,  "type": "question",    "question_number": 1, "follow_up": false, "text": "What is Big-O notation..."},
    {"t": 1.20,  "type": "answer",      "text": "Big-O notation describes..."},
    {"t": 3.45,  "type": "answer",      "text": "for example O of n"},
    {"t": 5.10,  "type": "screenshot",  "path": "images/deixis_...", "trigger_word": "this"},
    {"t": 6.00,  "type": "question",    "question_number": 1, "follow_up": true,  "text": "Can you give an example of an O(n^2) algorithm?"},
    {"t": 7.50,  "type": "answer",      "text": "Bubble sort is O of n squared"},
    {"t": 90.00, "type": "question",    "question_number": 2, "follow_up": false, "text": "What is the difference..."},
    ...
  ]
}
```

### Markdown (`final_transcript.md`)
Human-readable table with timestamps, suitable for a grader:

```
| Time  | Speaker  | Content                                              |
|-------|----------|------------------------------------------------------|
| 0:00  | EXAMINER | Q1: What is Big-O notation and why is it useful?    |
| 0:01  | STUDENT  | Big-O notation describes how fast an algorithm...   |
| 0:05  | [IMG]    | Screenshot: trigger word "this" → images/deixis_... |
| 1:00  | EXAMINER | Follow-up: Can you give an example of O(n^2)?       |
| 1:08  | STUDENT  | Bubble sort is O of n squared because...            |
```

---

## 8. Trigger-Word (Deixis) System

When the student says any of the configured trigger words while the camera is running, we capture a screenshot:

**Default trigger words:** `this`, `that`, `here`, `these`, `those`, `it`, `diagram`, `graph`, `figure`, `chart`, `table`

**How it works:**
1. During recording, every 3 seconds we transcribe the last 3 seconds with faster-whisper
2. If a trigger word appears in the transcript, `camera.capture_frame()` fires immediately
3. Screenshot is timestamped and saved: `images/deixis_<unix_ts>_<word>.jpg`
4. An entry is added to `vision_captures` in the response dict
5. The path appears in mini-transcripts and final transcript as evidence
6. Screenshots are **never sent to OpenAI**; they are evidence for the human reviewer

---

## 9. Video Recording

Continuous session video is recorded in the background:

| Setting | Value |
|---------|-------|
| FPS | 5 fps (low, saves RAM/CPU) |
| Resolution | 480 × 270 (16:9) |
| Codec | mp4v |
| Audio | `arecord` parallel WAV, muxed by ffmpeg at session end |
| Output | `/mnt/ssd/oral_exam_sessions/session_N/recording.mp4` |

The video + audio is the raw evidence. It is kept on the SSD and never sent anywhere automatically.

---

## 10. OpenAI API Calls

All API calls are text-only. No images, no audio, no video.

| Call | When | Input | Output |
|------|------|-------|--------|
| `generate_question` | Start of each question | system_prompt + rubric + question template | Question text to speak |
| `analyze_response` | After each answer | system_prompt + rubric + student transcript | Rubric coverage (Met/Partial/Missing per item) |
| `generate_follow_up` | When rubric items are Missing | system_prompt + rubric + mini-transcript text | Follow-up question text |
| `generate_grading_notes` | End of session | system_prompt + rubric + final_transcript.md | Structured grading notes |

**Model:** `gpt-4o-mini` (low latency, low cost, good at structured JSON responses)  
**Fallback:** `gpt-4o` if quality is insufficient

---

## 11. Component Summary

| Component | Technology | Runs on |
|-----------|-----------|---------|
| STT | faster-whisper `small.en` | Jetson CPU |
| TTS | Piper (`en_US-lessac-medium`) | Jetson Docker |
| Camera capture | OpenCV | Jetson |
| Video recording | OpenCV + arecord + ffmpeg | Jetson |
| LLM (analysis, follow-ups) | OpenAI GPT-4o-mini | Cloud |
| Session storage | `/mnt/ssd/oral_exam_sessions/` | 1 TB SSD |

---

## 12. Data Flow Summary

```
Teacher config (JSON)
        │
        ▼
[Session start] ── video recording starts ── audio recording starts
        │
        ▼
[OpenAI] ← system_prompt + rubric + "ask question 1"
        │
        ▼
[Piper TTS] speaks question  ──► Student hears question
        │
        ▼
[faster-whisper small.en] ← microphone audio (slices)
        │                         │
        │                         └── trigger words → [camera] → screenshot → images/
        ▼
 transcript segments (timestamped)
        │
        ▼
[Build mini-transcript] ── text events + screenshot paths
        │
        ▼
[OpenAI] ← mini-transcript text + rubric ► follow-up question
        │
        ▼
[Piper TTS] speaks follow-up ──► Student hears follow-up
        │
        ▼
[faster-whisper] ← student's follow-up answer
        │
        ▼
[Build final transcript] ── all events, all timestamps
        │
[Stop recording] ── ffmpeg mux ──► recording.mp4
        │
        ▼
session_N/ contains:
  recording.mp4          (video evidence)
  final_transcript.json  (structured, timestamped)
  final_transcript.md    (human-readable for grader)
  transcript.txt         (plain text)
  mini_transcripts/      (intermediate records)
  images/                (trigger-word screenshots)
```

---

## 13. Key Differences from V1

| Area | V1 | V2 |
|------|----|----|
| STT model | `base` (often misses words) | **`small.en`** (much better accuracy) |
| Vision model | Moondream via Ollama (removed) | **None** — screenshots only, OpenAI never sees images |
| LLM | Local Ollama (gemma2:2b / tinyllama, often fails on 8GB) | **OpenAI API only** |
| Storage | `WORKING_V1/data/` (eMMC) | **`/mnt/ssd/oral_exam_sessions/`** (1 TB SSD) |
| Exam config | Hardcoded in test scripts | **JSON config file per exam** |
| Question generation | Manual / hardcoded | **OpenAI generates from system_prompt + rubric** |
| Mini-transcript | Built from segments only | **Fallback to full text if segments missing** |
| RAM usage | ~5 GB (with Moondream) | **~3.5 GB** (STT + TTS + OpenCV only) |

---

## 14. File/Folder Structure (V2)

```
jetson_runtime/
├── PIPELINE.md                 ← this document
├── requirements.txt
├── config/
│   └── settings.py             ← all settings (SSD path, models, API, etc.)
├── stt/
│   ├── stt_service.py          ← faster-whisper small.en (persistent model)
│   └── audio_capture.py        ← audio recording utilities
├── tts/
│   └── tts_client.py           ← Piper TTS client
├── vlm/
│   └── camera.py               ← camera capture + continuous video recording
├── cloud_llm/
│   └── openai_client.py        ← all OpenAI calls (question gen, analysis, follow-up, grading)
├── proctor.py                  ← main orchestrator
├── session_manager.py          ← session ID + folder management (on SSD)
├── exams/
│   └── example_exam.json       ← example teacher config
└── tests/
    ├── test_stt.py
    ├── test_tts.py
    ├── test_camera.py
    └── test_openai.py
```

---

## 15. Running an Exam

```bash
# Start Piper TTS (one-time, if not running)
./start_tts.sh

# Run an exam
cd /home/dropouts/jetson_runtime
export OPENAI_API_KEY='your-key'
python3 proctor.py --exam exams/example_exam.json

# Results will be in:
ls /mnt/ssd/oral_exam_sessions/session_N/
```

---

## 16. STT Accuracy Tips

1. **Use `small.en`** — English-only model is more accurate than the multilingual `small` for English speech
2. **`initial_prompt`** — provide domain vocabulary so the model recognizes technical terms correctly  
   e.g. `"oral exam, Big-O notation, O of n, algorithm, complexity, merge sort, bubble sort"`
3. **`beam_size=5`** — default is fine; don't reduce below 3 or accuracy drops
4. **VAD padding 600 ms** — prevents the model from dropping first/last syllables of an answer
5. **Full-audio transcription** — always transcribe the complete merged audio at the end; don't rely only on partial chunk transcriptions
6. **If `small.en` is still not enough** — `medium.en` fits in RAM with careful management (~1.5 GB). Set `compute_type="int8"` to keep it fast on CPU.
