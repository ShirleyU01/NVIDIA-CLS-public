"""
jetson_runtime Configuration
"""
import os
from pathlib import Path

# ============================================================================
# DIRECTORIES
# ============================================================================
BASE_DIR = Path(__file__).parent.parent

# Exam configuration files (e.g. example_exam.json) live here.
EXAMS_DIR = BASE_DIR / "exams"
EXAMS_DIR.mkdir(parents=True, exist_ok=True)

# Session folders live inside jetson_runtime/sessions/session_N/
# Each session_N folder contains:
#   recording.mp4          — video + audio muxed
#   transcript.txt         — plain stitched text
#   transcript.json        — structured with segments
#   final_transcript.json  — timestamped chronological events
#   final_transcript.md    — human-readable table for grading
#   grading_notes.md       — OpenAI grading summary
#   images/                — trigger-word screenshots
#   mini_transcripts/      — mini_1.json, mini_2.json … (before each follow-up)
SESSIONS_DIR = BASE_DIR / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# Local cache for logs only
LOGS_DIR = BASE_DIR / "data" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# SPEECH-TO-TEXT  (faster-whisper small.en — already downloaded)
# ============================================================================
STT_MODEL = os.environ.get("ORAL_EXAM_STT_MODEL", "small")
STT_MODEL_LANGUAGE = "en"                  # lock to English (more accurate than auto-detect)
STT_DEVICE = os.environ.get("ORAL_EXAM_STT_DEVICE", "cpu")
STT_COMPUTE_TYPE = os.environ.get("ORAL_EXAM_STT_COMPUTE_TYPE", "int8")  # int8 on CPU: fast and low RAM
STT_BEAM_SIZE = 5
STT_VAD_FILTER = True
STT_VAD_SPEECH_PAD_MS = 600               # 600 ms padding each side — don't clip first/last word
STT_VAD_MIN_SILENCE_MS = 500
# Domain vocabulary hint — primes the model to recognise technical terms correctly
# A short, representative sentence in the domain — primes the model for technical vocabulary
# and prevents random hallucinations on near-silence. Keep it concise and natural.
STT_INITIAL_PROMPT = (
    "Big-O notation describes the worst-case runtime of an algorithm. "
    "For example, O of n, O of log n, O of n squared. "
    "Merge sort runs in O of n log n. Bubble sort is O of n squared."
)

# ============================================================================
# TEXT-TO-SPEECH  (Piper in Docker, localhost:5000)
# ============================================================================
TTS_URL = "http://localhost:5000"
TTS_VOICE = "en_US-lessac-medium"
TTS_CACHE_DIR = BASE_DIR / "data" / "tts_cache"
TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
TTS_MAX_CHUNK_CHARS = 200                  # split long text so Piper doesn't truncate
# Leading silence (ms) before the first TTS chunk so playback doesn't clip the first syllable.
TTS_LEADING_SILENCE_MS = int(os.environ.get("TTS_LEADING_SILENCE_MS", "2200"))
# Shorter pad before later chunks in the same utterance.
TTS_CHUNK_LEADING_SILENCE_MS = int(os.environ.get("TTS_CHUNK_LEADING_SILENCE_MS", "400"))
# Leading spaces sent to Piper so the first spoken word is not clipped (cache key includes this).
TTS_TEXT_LEADING_PAD = os.environ.get("TTS_TEXT_LEADING_PAD", "  ")

# ============================================================================
# OPENAI  (all LLM logic)
# ============================================================================
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
# Optional: use a different API endpoint (e.g. proxy, Azure, or another OpenAI-compatible API) for lower latency.
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "").strip() or None
# Accept either OPENAI_LLM_MODEL (oral exam) or EVIDENCE_PACKET_MODEL (integration pipeline)
# so one model env var works consistently in dev scripts.
# Use a faster/smaller model (e.g. gpt-5.4-mini) for low latency.
OPENAI_MODEL = (
    os.environ.get("OPENAI_LLM_MODEL")
    or os.environ.get("EVIDENCE_PACKET_MODEL")
    or "gpt-5.4-mini"
)
OPENAI_MAX_TOKENS = 600
OPENAI_TEMPERATURE = 0.4                   # low temperature → consistent, on-rubric responses
# Reasoning effort for GPT-5 family models ("minimal" | "low" | "medium" | "high").
# Default "low" keeps per-capture grading and post-session summaries snappy on Jetson.
OPENAI_REASONING_EFFORT = os.environ.get("OPENAI_REASONING_EFFORT", "low").strip() or "low"

# ============================================================================
# AUDIO / RECORDING
# ============================================================================
AUDIO_DEVICE = "pulse"                     # PulseAudio default source (USB mic set as default)
SAMPLE_RATE = 16000                        # Whisper prefers 16 kHz
AUDIO_FORMAT = "S16_LE"
CHANNELS = 1

MAX_RESPONSE_TIME = 60                     # seconds a student has to answer
RECORDING_SLICE_SEC = 1                    # record in 1-second slices for fast Enter-to-stop
TRIGGER_TRANSCRIBE_SLICES = 3             # transcribe every 3 s for trigger-word detection
DONE_PHRASES = [
    "i'm done", "im done", "i am done", "that's all", "thats all",
    "i'm finished", "im finished", "next question", "done",
]
ENABLE_KEYBOARD_DONE = True                # press Enter in terminal to stop recording early

# ============================================================================
# CAMERA / VIDEO
# ============================================================================
CAMERA_DEVICE = "/dev/video0"
CAMERA_RESOLUTION = (640, 480)             # for trigger-word screenshots
CAMERA_FPS = 10
VIDEO_RECORDING_FPS = 5                    # continuous session video (low FPS saves CPU)
VIDEO_RECORDING_RESOLUTION = (480, 270)    # 16:9 low-res (saves storage)
VIDEO_RECORDING_FOURCC = "mp4v"

# ============================================================================
# DEIXIS / TRIGGER WORDS
# ============================================================================
DEICTIC_KEYWORDS = [
    "this", "that", "here", "these", "those", "it",
    "diagram", "graph", "figure", "chart", "table",
]

# ============================================================================
# EXAM SETTINGS
# ============================================================================
ENABLE_VISION = True
ENABLE_FOLLOW_UPS = True
MAX_FOLLOW_UPS = 1
# If student explicitly ends a response ("I'm done" button, spoken done phrase,
# or Enter in terminal), treat that as final for this question and do not
# generate additional follow-up prompts.
SKIP_FOLLOW_UPS_ON_DONE_SIGNAL = False

# ============================================================================
# SPOKEN PROMPTS (Jetson TTS)
# ============================================================================
# When true, the proctor speaks the full question text aloud (current behavior).
# When false, the proctor speaks only short instructions and expects the question
# to be shown in the UI / on paper (faster, avoids long TTS synthesis).
SPEAK_QUESTION_TEXT = True

# Short instruction spoken before each question when SPEAK_QUESTION_TEXT=False.
INSTRUCTION_BEFORE_QUESTION = (
    "Here is the question. Please read it carefully. "
    "Work it out on paper. "
    "When you're ready, start explaining your solution out loud. "
    "Say 'I'm done' when you finish."
)

# ============================================================================
# STUDY GUIDE (paper capture mode)
# ============================================================================
# Study mode should speak only short instructions (never the full question).
STUDY_GUIDE_SPEAK_INSTRUCTIONS = True
STUDY_GUIDE_INSTRUCTIONS = (
    "Study mode. Solve the problem on paper. "
    "When you're ready, hold your paper up to the camera so it fills the frame. "
    "Then press Capture and grade."
)

# ============================================================================
# LOGGING
# ============================================================================
LOG_LEVEL = "INFO"
LOG_FILE = LOGS_DIR / "oral_exam_v2.log"
