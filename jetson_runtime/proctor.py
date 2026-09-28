"""
jetson_runtime Oral Exam Proctor
Orchestrates STT (local small.en) + TTS (local Piper) + OpenAI (cloud LLM)

Flow per question:
  1. OpenAI generates spoken question from rubric
  2. TTS speaks it
  3. Student answers (sliced recording, Enter or "I'm done" to stop)
     - Every 3s: transcribe partial audio for trigger-word detection → screenshot
  4. Full answer transcribed with faster-whisper small.en
  5. OpenAI analyzes answer against rubric
  6. For each missing rubric item (up to max_follow_ups):
       - Build mini-transcript (timestamped text + screenshot paths)
       - OpenAI generates follow-up question
       - TTS speaks it; student answers; repeat steps 3-4
  7. At session end: build final_transcript.json/.md, mux recording.mp4
"""
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import settings
from session_manager import get_next_session_id
from stt.stt_service import get_stt_service
from stt.audio_capture import get_audio_capture
from tts.tts_client import get_tts_client
from vlm.camera import get_camera
import cloud_llm.openai_client as llm_api

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(settings.LOG_FILE),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class OralExamProctor:
    """
    Full V2 oral exam proctor.

    Attributes set at construction:
        enable_vision: bool — whether to run the camera / screenshot system
    Attributes set at exam start (conduct_exam):
        _session_id, _session_images_dir, _session_audio_process, _system_prompt
    """

    def __init__(self, enable_vision: bool = None, enable_keyboard_done: bool = None):
        logger.info("=" * 70)
        logger.info("Initializing jetson_runtime Oral Exam Proctor")
        logger.info("=" * 70)

        self.enable_vision = enable_vision if enable_vision is not None else settings.ENABLE_VISION
        self.enable_keyboard_done = (
            enable_keyboard_done if enable_keyboard_done is not None else settings.ENABLE_KEYBOARD_DONE
        )

        logger.info("Loading STT model (%s)…", settings.STT_MODEL)
        self.stt = get_stt_service()
        self.audio = get_audio_capture()
        self.tts = get_tts_client()

        if self.enable_vision:
            self.camera = get_camera()
            self.camera.open()

        self._session_id: str = None
        self._session_images_dir: Path = None
        self._session_audio_process = None
        self._system_prompt: str = ""
        # Set by external controllers (e.g. Jetson web UI) to stop listening early.
        self._external_done = threading.Event()
        # Set by external controllers to terminate the current exam ASAP.
        self._stop_requested = threading.Event()
        # Live status fields consumed by Jetson backend polling.
        self._state_lock = threading.Lock()
        self._stt_lock = threading.Lock()
        self._live_status = "idle"
        self._live_question = ""
        self._live_transcript_preview = ""

        logger.info("✅ All services ready.")
        logger.info("=" * 70)

    def request_done(self) -> None:
        """
        Signal the proctor that the student is done speaking for the current response.

        This mirrors the "press Enter when done" terminal workflow, but can be
        invoked from a web UI via the Jetson backend.
        """
        self._external_done.set()

    def request_stop(self) -> None:
        """
        Signal that the whole exam should stop as soon as possible.
        """
        self._stop_requested.set()
        self._external_done.set()

    def get_live_state(self) -> dict:
        with self._state_lock:
            return {
                "status": self._live_status,
                "question": self._live_question,
                "transcript_preview": self._live_transcript_preview,
            }

    def _set_live_state(
        self,
        *,
        status: str | None = None,
        question: str | None = None,
        transcript_preview: str | None = None,
    ) -> None:
        with self._state_lock:
            if status is not None:
                self._live_status = status
            if question is not None:
                self._live_question = question
            if transcript_preview is not None:
                self._live_transcript_preview = transcript_preview

    # ------------------------------------------------------------------ #
    #  TTS helpers
    # ------------------------------------------------------------------ #

    def _speak(self, text: str):
        logger.info("TTS: %s", text[:100])
        self.tts.speak(text)

    # ------------------------------------------------------------------ #
    #  Session folder management
    # ------------------------------------------------------------------ #

    def _ensure_session_folder(self) -> Path:
        """Create session/images dir on first call; start video/audio recording."""
        if self._session_images_dir is not None and self._session_images_dir.exists():
            return self._session_images_dir
        if self._session_id is None:
            self._session_id = get_next_session_id()
        self._session_images_dir = settings.SESSIONS_DIR / self._session_id / "images"
        self._session_images_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Session folder: %s", self._session_images_dir.parent)
        if self.enable_vision and not self.camera.is_recording():
            video_path = self._session_images_dir.parent / "recording.mp4"
            self.camera.start_recording(video_path)
            self._start_audio_recording()
        return self._session_images_dir

    def _start_audio_recording(self):
        """Start a long-running arecord for the session audio (muxed into video later)."""
        if self._session_audio_process is not None:
            return
        session_dir = self._session_images_dir.parent
        audio_path = session_dir / "audio_temp.wav"
        try:
            cmd = [
                "arecord",
                "-D", settings.AUDIO_DEVICE,
                "-d", "3600",
                "-r", str(settings.SAMPLE_RATE),
                "-f", settings.AUDIO_FORMAT,
                "-c", str(settings.CHANNELS),
                "-t", "wav",
                "-q",
                str(audio_path),
            ]
            self._session_audio_process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            logger.info("Session audio recording started → %s", audio_path)
        except Exception as e:
            logger.warning("Could not start session audio recording: %s", e)

    def _stop_audio_and_mux(self):
        """Stop arecord and mux audio track into recording.mp4 with ffmpeg."""
        if self._session_audio_process is not None:
            try:
                self._session_audio_process.terminate()
                self._session_audio_process.wait(timeout=5)
            except Exception:
                try:
                    self._session_audio_process.kill()
                except Exception:
                    pass
            self._session_audio_process = None

        session_dir = self._session_images_dir.parent if self._session_images_dir else None
        if not session_dir:
            return
        video_path = session_dir / "recording.mp4"
        audio_path = session_dir / "audio_temp.wav"
        if not video_path.exists() or not audio_path.exists():
            if audio_path.exists():
                try:
                    os.unlink(audio_path)
                except Exception:
                    pass
            return
        out_path = session_dir / "recording_muxed.mp4"
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", str(video_path),
                    "-i", str(audio_path),
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-shortest",
                    str(out_path),
                ],
                capture_output=True,
                timeout=120,
            )
            if out_path.exists():
                os.replace(out_path, video_path)
                logger.info("Video muxed with audio: %s", video_path)
            try:
                os.unlink(audio_path)
            except Exception:
                pass
        except Exception as e:
            logger.warning("ffmpeg mux failed (is ffmpeg installed?): %s", e)

    # ------------------------------------------------------------------ #
    #  Deictic / trigger-word detection
    # ------------------------------------------------------------------ #

    def _detect_deictic(
        self,
        transcript: str,
        segments: list,
        chunk_start_time: float,
        response_start_time: float,
    ) -> list:
        """
        Find trigger words in transcript → capture screenshot.
        Returns list of capture dicts with absolute_time (seconds from response start).
        """
        captures = []
        pattern = r"\b(" + "|".join(re.escape(k) for k in settings.DEICTIC_KEYWORDS) + r")\b"
        for match in re.finditer(pattern, transcript, re.IGNORECASE):
            word = match.group(0)
            pos = match.start()
            char_count = 0
            timestamp = 0.0
            phrase = transcript
            for seg in segments:
                seg_text = seg.get("text", "")
                if char_count <= pos < char_count + len(seg_text):
                    timestamp = seg.get("start", 0.0)
                    phrase = seg_text
                    break
                char_count += len(seg_text) + 1
            try:
                images_dir = self._ensure_session_folder()
                frame_file = images_dir / f"deixis_{int(time.time() * 1000)}_{word}_{pos}.jpg"
                captured = self.camera.capture_frame(str(frame_file))
                if captured:
                    absolute_ts = chunk_start_time - response_start_time + timestamp
                    captures.append({
                        "word": word,
                        "timestamp": timestamp,
                        "absolute_time": round(absolute_ts, 2),
                        "phrase": phrase,
                        "image": captured,
                    })
                    logger.info("Screenshot captured for trigger word '%s' → %s", word, frame_file.name)
            except Exception as e:
                logger.error("Screenshot capture failed: %s", e)
        return captures

    # ------------------------------------------------------------------ #
    #  Listening / recording
    # ------------------------------------------------------------------ #

    def listen_for_response(self, duration: int = None) -> dict:
        """
        Record the student's answer.

        - Records in 1-second slices (RECORDING_SLICE_SEC).
        - Stops when Enter is pressed (within ~1s) OR when "I'm done" is heard OR max duration reached.
        - Every TRIGGER_TRANSCRIBE_SLICES seconds: transcribe partial audio to detect trigger words → screenshot.
        - After recording: final full-audio transcription for maximum accuracy.

        Returns:
            {text, segments, vision_captures, duration, transcription_times}
        """
        if duration is None:
            duration = settings.MAX_RESPONSE_TIME

        # Clear stale "done speaking" signal between questions, unless a full
        # exam stop has been requested.
        if not self._stop_requested.is_set():
            self._external_done.clear()
        self._set_live_state(status="listening")

        use_keyboard = self.enable_keyboard_done and sys.stdin.isatty()
        slice_sec = settings.RECORDING_SLICE_SEC
        trigger_slices = settings.TRIGGER_TRANSCRIBE_SLICES

        print(f"\n{'—'*60}")
        if use_keyboard:
            print("  ▶ Recording — press Enter when done (or say 'I'm done')")
        else:
            print(f"  ▶ Recording — max {duration}s (say 'I'm done' to stop early)")
        print(f"{'—'*60}\n")

        keyboard_done = threading.Event()

        def _wait_enter():
            try:
                input()
                keyboard_done.set()
            except (EOFError, KeyboardInterrupt):
                pass

        if use_keyboard:
            t = threading.Thread(target=_wait_enter, daemon=True)
            t.start()

        slice_paths: list = []
        vision_captures: list = []
        transcription_times: list = []
        start_time = time.time()
        max_slices = (duration + slice_sec - 1) // slice_sec

        # Partial STT state — runs in a background thread so recording is NEVER blocked.
        # Only one partial job runs at a time; if the previous one is still running we skip
        # the new trigger check (we'll catch it on the next slice boundary).
        _partial_thread: threading.Thread = None
        _partial_lock = threading.Lock()

        def _run_partial_stt(paths_snapshot: list, chunk_start_t: float):
            if not self._stt_lock.acquire(blocking=False):
                return
            fd, merged = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            try:
                self.audio.merge_wavs(paths_snapshot, merged)
                partial = self.stt.transcribe(merged)
                text = (partial.get("text") or "").strip()
                if text:
                    logger.info("[Partial for triggers] %s", text)
                    if self.enable_vision:
                        caps = self._detect_deictic(
                            text, partial.get("segments", []),
                            chunk_start_t, start_time,
                        )
                        with _partial_lock:
                            vision_captures.extend(caps)
                    if any(p in text.lower() for p in settings.DONE_PHRASES):
                        keyboard_done.set()
            except Exception as e:
                logger.debug("Partial STT error: %s", e)
            finally:
                self._stt_lock.release()
                try:
                    os.unlink(merged)
                except Exception:
                    pass

        while (
            len(slice_paths) < max_slices
            and not keyboard_done.is_set()
            and not self._external_done.is_set()
            and not self._stop_requested.is_set()
        ):
            wav = self.audio.record(slice_sec)
            slice_paths.append(wav)

            # Kick off a background partial transcription every trigger_slices slices,
            # but only if the previous partial job has already finished.
            if len(slice_paths) >= trigger_slices and (
                _partial_thread is None or not _partial_thread.is_alive()
            ):
                recent_snapshot = list(slice_paths[-trigger_slices:])
                chunk_start_t = start_time + (len(slice_paths) - trigger_slices) * slice_sec
                _partial_thread = threading.Thread(
                    target=_run_partial_stt,
                    args=(recent_snapshot, chunk_start_t),
                    daemon=True,
                )
                _partial_thread.start()

        elapsed = time.time() - start_time
        done_signal = keyboard_done.is_set() or self._external_done.is_set()

        # Final full-audio transcription
        full_text = ""
        all_segments: list = []
        if slice_paths:
            fd, merged_all = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            try:
                self.audio.merge_wavs(slice_paths, merged_all)
                with self._stt_lock:
                    result = self.stt.transcribe(merged_all)
                full_text = (result.get("text") or "").strip()
                if result.get("transcription_time"):
                    transcription_times.append(result["transcription_time"])
                for seg in result.get("segments", []):
                    seg["absolute_time"] = seg.get("start", 0.0)
                    all_segments.append(seg)
            finally:
                try:
                    os.unlink(merged_all)
                except Exception:
                    pass
            for p in slice_paths:
                try:
                    os.unlink(p)
                except Exception:
                    pass

        sep = "=" * 60
        print(f"\n{sep}")
        print("  TRANSCRIPT")
        print(sep)
        print(f"  {full_text if full_text else '(no speech detected)'}")
        print(f"{sep}\n")

        return {
            "text": full_text,
            "segments": all_segments,
            "vision_captures": vision_captures,
            "duration": elapsed,
            "transcription_times": transcription_times,
            "done_signal": done_signal,
        }

    # ------------------------------------------------------------------ #
    #  Mini-transcript helpers
    # ------------------------------------------------------------------ #

    def _build_mini_transcript_events(self, responses: list, time_offset: float = 0.0) -> list:
        """
        Build a chronological list of timestamped events from one or more responses.
        Includes both text segments and screenshot references.
        Falls back to full response text if no segments (robustness fix from V1).
        """
        events = []
        t_offset = time_offset
        for resp in responses:
            added_text = False
            for seg in resp.get("segments", []):
                t = t_offset + seg.get("absolute_time", seg.get("start", 0.0))
                text = (seg.get("text") or "").strip()
                if text:
                    events.append({"t": round(t, 2), "type": "text", "text": text})
                    added_text = True
            for cap in resp.get("vision_captures", []):
                t = t_offset + cap.get("absolute_time", cap.get("timestamp", 0.0))
                rel_path = "images/" + Path(cap.get("image") or "").name
                events.append({
                    "t": round(t, 2),
                    "type": "screenshot",
                    "path": rel_path,
                    "trigger_word": cap.get("word", ""),
                })
            if not added_text and (resp.get("text") or "").strip():
                events.append({"t": round(t_offset, 2), "type": "text", "text": resp["text"].strip()})
            t_offset += resp.get("duration", 0.0) + 1.0
        events.sort(key=lambda e: e["t"])
        return events

    def _mini_transcript_text(self, events: list) -> str:
        """Plain text version of mini-transcript: text events plus diagram/screenshot refs (path and trigger word) so follow-up generation has full context."""
        lines = []
        for e in events:
            if e.get("type") == "text":
                ts = e.get("t", 0.0)
                lines.append(f"[{ts:.1f}s] {e['text']}")
            elif e.get("type") == "screenshot":
                ts = e.get("t", 0.0)
                trigger = e.get("trigger_word", "").strip()
                path = e.get("path", "")
                if path:
                    lines.append(f"[{ts:.1f}s] [diagram/screenshot: {path}" + (f", triggered by \"{trigger}\"" if trigger else "") + "]")
                else:
                    lines.append(f"[{ts:.1f}s] [diagram/screenshot triggered by \"{trigger}\"]")
        return "\n".join(lines)

    def _save_mini_transcript(
        self, events: list, question: str, rubric_items: list, index: int
    ) -> Path:
        """Save mini-transcript JSON to session folder. Returns path (or None if no session)."""
        if self._session_images_dir is None:
            return None
        session_dir = self._session_images_dir.parent
        mini_dir = session_dir / "mini_transcripts"
        mini_dir.mkdir(parents=True, exist_ok=True)
        path = mini_dir / f"mini_{index}.json"
        path.write_text(
            json.dumps({"question": question, "rubric_items": rubric_items, "events": events}, indent=2),
            encoding="utf-8",
        )
        logger.info("Mini-transcript saved: %s (%d events)", path, len(events))
        return path

    # ------------------------------------------------------------------ #
    #  Final transcript helpers
    # ------------------------------------------------------------------ #

    def _build_final_events(self, exam_data: dict) -> list:
        """Chronological events (question / answer / screenshot) for the whole exam."""
        events = []
        t = 0.0
        for i, q in enumerate(exam_data.get("questions", []), 1):
            events.append({"t": round(t, 2), "type": "question",
                           "question_number": i, "follow_up": False,
                           "text": q.get("question", "")})
            t += 1.0
            for r in q.get("responses", []):
                added = False
                for seg in r.get("segments", []):
                    st = t + seg.get("absolute_time", seg.get("start", 0.0))
                    if (seg.get("text") or "").strip():
                        events.append({"t": round(st, 2), "type": "answer",
                                       "text": seg["text"].strip()})
                        added = True
                for cap in r.get("vision_captures", []):
                    ct = t + cap.get("absolute_time", cap.get("timestamp", 0.0))
                    events.append({"t": round(ct, 2), "type": "screenshot",
                                   "path": "images/" + Path(cap.get("image") or "").name,
                                   "trigger_word": cap.get("word", "")})
                if not added and (r.get("text") or "").strip():
                    events.append({"t": round(t, 2), "type": "answer", "text": r["text"].strip()})
                t += r.get("duration", 0.0) + 1.0
            for fu in q.get("follow_ups", []):
                events.append({"t": round(t, 2), "type": "question",
                               "question_number": i, "follow_up": True,
                               "text": fu.get("question", "")})
                t += 1.0
                resp = fu.get("response", {})
                added = False
                for seg in resp.get("segments", []):
                    st = t + seg.get("absolute_time", seg.get("start", 0.0))
                    if (seg.get("text") or "").strip():
                        events.append({"t": round(st, 2), "type": "answer",
                                       "text": seg["text"].strip()})
                        added = True
                for cap in resp.get("vision_captures", []):
                    ct = t + cap.get("absolute_time", cap.get("timestamp", 0.0))
                    events.append({"t": round(ct, 2), "type": "screenshot",
                                   "path": "images/" + Path(cap.get("image") or "").name,
                                   "trigger_word": cap.get("word", "")})
                if not added and (resp.get("text") or "").strip():
                    events.append({"t": round(t, 2), "type": "answer", "text": resp["text"].strip()})
                t += resp.get("duration", 0.0) + 1.0

        # Post-exam follow-ups are global (not tied to a specific base question).
        for fu in exam_data.get("post_exam_follow_ups", []):
            events.append(
                {
                    "t": round(t, 2),
                    "type": "question",
                    "question_number": None,
                    "follow_up": True,
                    "follow_up_scope": "global",
                    "text": fu.get("question", ""),
                }
            )
            t += 1.0
            resp = fu.get("response", {}) or {}
            added = False
            for seg in resp.get("segments", []):
                st = t + seg.get("absolute_time", seg.get("start", 0.0))
                if (seg.get("text") or "").strip():
                    events.append({"t": round(st, 2), "type": "answer", "text": seg["text"].strip()})
                    added = True
            for cap in resp.get("vision_captures", []):
                ct = t + cap.get("absolute_time", cap.get("timestamp", 0.0))
                events.append(
                    {
                        "t": round(ct, 2),
                        "type": "screenshot",
                        "path": "images/" + Path(cap.get("image") or "").name,
                        "trigger_word": cap.get("word", ""),
                    }
                )
            if not added and (resp.get("text") or "").strip():
                events.append({"t": round(t, 2), "type": "answer", "text": resp["text"].strip()})
            t += resp.get("duration", 0.0) + 1.0
        events.sort(key=lambda e: (e["t"], 0 if e["type"] == "screenshot" else 1))
        return events

    def _events_to_markdown(self, events: list, exam_id: str = "") -> str:
        lines = [
            f"# Oral Exam Transcript — {exam_id}",
            "",
            "| Time | Speaker | Content |",
            "|------|---------|---------|",
        ]
        for e in events:
            t = e.get("t", 0.0)
            ts = f"{int(t // 60)}:{t % 60:05.2f}"
            etype = e.get("type")
            if etype == "question":
                label = "Follow-up" if e.get("follow_up") else f"Q{e.get('question_number', '')}"
                text = (e.get("text") or "").replace("|", "\\|")
                lines.append(f"| {ts} | **EXAMINER** | **{label}:** {text} |")
            elif etype == "answer":
                text = (e.get("text") or "").replace("|", "\\|")
                lines.append(f"| {ts} | STUDENT | {text} |")
            elif etype == "screenshot":
                word = e.get("trigger_word", "")
                path = e.get("path", "")
                lines.append(f"| {ts} | [IMG] | Screenshot (trigger: \"{word}\") → `{path}` |")
        return "\n".join(lines)

    def _save_session_transcript(self, exam_id: str, exam_data: dict):
        """Write all transcript files to the session folder."""
        session_dir = settings.SESSIONS_DIR / exam_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Plain text
        lines = []
        for i, q in enumerate(exam_data.get("questions", []), 1):
            lines.append(f"Q{i}: {q.get('question', '')}")
            for r in q.get("responses", []):
                if r.get("text", "").strip():
                    lines.append(f"  Student: {r['text'].strip()}")
            for fu in q.get("follow_ups", []):
                lines.append(f"  Follow-up: {fu.get('question', '')}")
                if fu.get("response", {}).get("text", "").strip():
                    lines.append(f"  Student: {fu['response']['text'].strip()}")
            lines.append("")
        for i, fu in enumerate(exam_data.get("post_exam_follow_ups", []), 1):
            lines.append(f"Post-exam follow-up {i}: {fu.get('question', '')}")
            if fu.get("response", {}).get("text", "").strip():
                lines.append(f"  Student: {fu['response']['text'].strip()}")
            lines.append("")
        (session_dir / "transcript.txt").write_text("\n".join(lines).strip(), encoding="utf-8")

        # Structured JSON
        structured = {
            "exam_id": exam_id,
            "session_id": self._session_id,
            "start_time": exam_data.get("start_time"),
            "end_time": exam_data.get("end_time"),
            "questions": [],
            "post_exam_follow_ups": [],
        }
        for q in exam_data.get("questions", []):
            structured["questions"].append({
                "question": q.get("question", ""),
                "rubric_items": q.get("rubric_items", []),
                "responses": [
                    {"text": r.get("text", ""), "duration": r.get("duration"),
                     "segments": r.get("segments", [])}
                    for r in q.get("responses", [])
                ],
                "follow_ups": [
                    {"question": fu.get("question", ""),
                     "response_text": fu.get("response", {}).get("text", ""),
                     "response_segments": fu.get("response", {}).get("segments", [])}
                    for fu in q.get("follow_ups", [])
                ],
                "final_analysis": q.get("final_analysis", {}),
            })
        for fu in exam_data.get("post_exam_follow_ups", []):
            structured["post_exam_follow_ups"].append(
                {
                    "question": fu.get("question", ""),
                    "response_text": fu.get("response", {}).get("text", ""),
                    "response_segments": fu.get("response", {}).get("segments", []),
                    "missing_items": fu.get("missing_items", []),
                }
            )
        (session_dir / "transcript.json").write_text(
            json.dumps(structured, indent=2), encoding="utf-8"
        )

        # Final transcript (timestamped events)
        events = self._build_final_events(exam_data)
        (session_dir / "final_transcript.json").write_text(
            json.dumps({
                "exam_id": exam_id,
                "session_id": self._session_id,
                "start_time": exam_data.get("start_time"),
                "end_time": exam_data.get("end_time"),
                "events": events,
            }, indent=2),
            encoding="utf-8",
        )
        md = self._events_to_markdown(events, exam_id)
        (session_dir / "final_transcript.md").write_text(md, encoding="utf-8")

        logger.info("All transcripts saved to: %s", session_dir)
        logger.info("  transcript.txt / transcript.json / final_transcript.json / final_transcript.md")

    # ------------------------------------------------------------------ #
    #  save_final_transcript (for single-question test runs)
    # ------------------------------------------------------------------ #

    def save_final_transcript(self, question_result: dict):
        """
        Save transcripts for a single-question session (e.g. test_one_question.py).
        Call after conduct_question() when a session folder is active.
        """
        if not self._session_id:
            return
        self._save_session_transcript(self._session_id, {
            "exam_id": self._session_id,
            "start_time": question_result.get("start_time"),
            "end_time": question_result.get("end_time"),
            "questions": [{
                "question": question_result.get("question", ""),
                "rubric_items": question_result.get("rubric_items", []),
                "responses": question_result.get("responses", []),
                "follow_ups": question_result.get("follow_ups", []),
                "final_analysis": question_result.get("final_analysis", {}),
            }],
        })

    # ------------------------------------------------------------------ #
    #  conduct_question
    # ------------------------------------------------------------------ #

    def conduct_question(
        self,
        question: str,
        rubric_items: list,
        system_prompt: str = "",
        max_follow_ups: int = None,
        lecture_material: str = "",
    ) -> dict:
        """
        Ask one question, listen, analyze, do follow-ups.

        Args:
            question:       Question text (already generated or from config)
            rubric_items:   List of rubric strings
            system_prompt:  OpenAI system prompt for analysis / follow-ups
            max_follow_ups: Override settings.MAX_FOLLOW_UPS
            lecture_material: Optional source material for follow-ups and analysis

        Returns dict with: question, rubric_items, responses, follow_ups,
                           initial_analysis, final_analysis, start_time, end_time
        """
        if max_follow_ups is None:
            max_follow_ups = settings.MAX_FOLLOW_UPS
        sp = system_prompt or self._system_prompt

        result = {
            "question": question,
            "rubric_items": rubric_items,
            "start_time": datetime.now().isoformat(),
            "responses": [],
            "follow_ups": [],
            "initial_analysis": {},
            "final_analysis": {},
        }

        if self._stop_requested.is_set():
            result["end_time"] = datetime.now().isoformat()
            return result

        # Ask
        self._set_live_state(status="speaking", question=question)
        if settings.SPEAK_QUESTION_TEXT:
            self._speak(question)
        else:
            # Speak only short instructions; the question is expected to be shown elsewhere (UI/paper).
            self._speak(settings.INSTRUCTION_BEFORE_QUESTION)
        time.sleep(0.5)

        # Listen
        response = self.listen_for_response()
        result["responses"].append(response)
        self._set_live_state(transcript_preview=(response.get("text", "") or "")[:200])

        if self._stop_requested.is_set():
            result["end_time"] = datetime.now().isoformat()
            return result

        if not response["text"].strip():
            self._speak("I didn't catch that. Could you please repeat your answer?")
            result["end_time"] = datetime.now().isoformat()
            return result

        # Analyze initial response
        self._set_live_state(status="thinking")
        logger.info("Analyzing response with OpenAI…")
        analysis = llm_api.analyze_response(
            system_prompt=sp,
            question=question,
            rubric_items=rubric_items,
            student_transcript=response["text"],
            lecture_material=lecture_material,
        )
        result["initial_analysis"] = analysis

        missing = [
            item["item"] for item in analysis.get("items", [])
            if item.get("status") in ("Missing", "Partial")
        ]

        # If the student explicitly signaled completion, treat this response as
        # final for the current question and skip follow-ups.
        if settings.SKIP_FOLLOW_UPS_ON_DONE_SIGNAL and response.get("done_signal"):
            result["final_analysis"] = analysis
            result["end_time"] = datetime.now().isoformat()
            return result

        # Follow-up loop
        follow_up_count = 0
        current_response = response

        while (
            settings.ENABLE_FOLLOW_UPS
            and missing
            and follow_up_count < max_follow_ups
            and not self._stop_requested.is_set()
        ):
            # Build mini-transcript of everything said so far for this question
            all_responses = [response] + [fu["response"] for fu in result["follow_ups"]]
            events = self._build_mini_transcript_events(all_responses)
            self._save_mini_transcript(events, question, rubric_items, index=follow_up_count + 1)
            mini_text = self._mini_transcript_text(events)

            logger.info("Generating follow-up %d / %d…", follow_up_count + 1, max_follow_ups)
            already_asked = [fu.get("question", "") for fu in result["follow_ups"] if fu.get("question")]
            follow_up_q = llm_api.generate_follow_up(
                system_prompt=sp,
                question=question,
                rubric_items=rubric_items,
                missing_items=missing,
                mini_transcript_text=mini_text,
                lecture_material=lecture_material,
                already_asked_follow_ups=already_asked,
            )
            if not follow_up_q:
                break

            self._set_live_state(status="speaking", question=follow_up_q)
            self._speak(follow_up_q)
            time.sleep(0.5)

            fu_response = self.listen_for_response()
            result["follow_ups"].append({"question": follow_up_q, "response": fu_response})
            self._set_live_state(
                transcript_preview=(fu_response.get("text", "") or "")[:200],
                status="thinking",
            )

            # Re-analyze with all text so far
            combined_text = " ".join(
                [response["text"]] + [fu["response"]["text"] for fu in result["follow_ups"]]
            )
            analysis = llm_api.analyze_response(
                system_prompt=sp,
                question=question,
                rubric_items=rubric_items,
                student_transcript=combined_text,
            )
            missing = [
                item["item"] for item in analysis.get("items", [])
                if item.get("status") in ("Missing", "Partial")
            ]
            follow_up_count += 1

        result["final_analysis"] = analysis
        result["end_time"] = datetime.now().isoformat()
        return result

    # ------------------------------------------------------------------ #
    #  conduct_exam  (main entry point)
    # ------------------------------------------------------------------ #

    def conduct_exam(self, exam_config: dict) -> dict:
        """
        Run a full exam from a config dict.

        exam_config keys:
            exam_id, subject, system_prompt, questions (list of {text, rubric_items, max_follow_ups})

        Returns exam_data dict with all results.
        """
        exam_id = exam_config.get("exam_id") or get_next_session_id()
        self._session_id = exam_id
        self._system_prompt = exam_config.get("system_prompt", "")
        self._stop_requested.clear()
        self._set_live_state(status="speaking", question="", transcript_preview="")

        # Initialise session folder + recording
        self._ensure_session_folder()
        session_dir = settings.SESSIONS_DIR / exam_id
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "exam_config.json").write_text(
            json.dumps(exam_config, indent=2), encoding="utf-8"
        )

        exam_data = {
            "exam_id": exam_id,
            "subject": exam_config.get("subject", ""),
            "start_time": datetime.now().isoformat(),
            "questions": [],
            "post_exam_follow_ups": [],
            "status": "in_progress",
        }

        logger.info("Starting exam: %s | %s", exam_id, exam_config.get("subject", ""))

        # Greeting
        greeting = (
            "Hello! I'm your AI oral exam proctor. "
            "I'll ask you a series of questions. Please answer each one in your own words. "
            "Take your time. Say 'I'm done' or press Enter when you've finished answering. "
            "Let's begin."
        )
        self._speak(greeting)
        time.sleep(2)

        questions = exam_config.get("questions", [])
        for i, q_data in enumerate(questions, 1):
            if self._stop_requested.is_set():
                break
            if len(questions) > 1:
                time.sleep(0.5)

            question_text = q_data.get("text", "")
            rubric_items = q_data.get("rubric_items", [])
            lecture_material = exam_config.get("lecture_material") or ""

            # Ask main question with configurable per-question follow-ups.
            # Default remains 2 unless overridden by question config.
            q_max_follow_ups = q_data.get("max_follow_ups", settings.MAX_FOLLOW_UPS)
            try:
                q_max_follow_ups = max(0, int(q_max_follow_ups))
            except Exception:
                q_max_follow_ups = settings.MAX_FOLLOW_UPS

            result = self.conduct_question(
                question=question_text,
                rubric_items=rubric_items,
                system_prompt=self._system_prompt,
                max_follow_ups=q_max_follow_ups,
                lecture_material=lecture_material,
            )
            exam_data["questions"].append(result)
            if self._stop_requested.is_set():
                break

            if i < len(questions):
                self._speak("Thank you. Moving to the next question.")
                time.sleep(1.5)

        # After all main questions: ask a fixed number of follow-ups that probe missing rubric/lecture content across the whole exam
        post_exam_follow_ups = int(exam_config.get("post_exam_follow_ups", 1))
        if (
            not self._stop_requested.is_set()
            and settings.ENABLE_FOLLOW_UPS
            and post_exam_follow_ups > 0
            and exam_data["questions"]
        ):
            # Union of all rubric items from all questions (for analysis and follow-up generation)
            all_rubric_items = []
            seen = set()
            for q_data in questions:
                for item in q_data.get("rubric_items", []):
                    if item not in seen:
                        seen.add(item)
                        all_rubric_items.append(item)
            lecture_material = exam_config.get("lecture_material") or ""
            sp = self._system_prompt
            for fu_round in range(post_exam_follow_ups):
                if self._stop_requested.is_set():
                    break
                # All responses so far: every main answer + every post-exam follow-up answer
                all_responses = [
                    r for q in exam_data["questions"] for r in q.get("responses", [])
                ]
                all_responses += [
                    fu["response"] for fu in exam_data.get("post_exam_follow_ups", [])
                    if isinstance(fu, dict) and isinstance(fu.get("response"), dict)
                ]
                combined_text = " ".join((r.get("text") or "").strip() for r in all_responses)

                if not combined_text.strip():
                    break

                self._set_live_state(status="thinking")
                logger.info("Analyzing full transcript for post-exam follow-up %d/%d…", fu_round + 1, post_exam_follow_ups)
                analysis = llm_api.analyze_response(
                    system_prompt=sp,
                    question="Based on the questions so far.",
                    rubric_items=all_rubric_items,
                    student_transcript=combined_text,
                    lecture_material=lecture_material,
                )
                missing = [
                    item["item"] for item in analysis.get("items", [])
                    if item.get("status") in ("Missing", "Partial")
                ]
                if not missing:
                    logger.info("No missing rubric items; skipping remaining post-exam follow-ups.")
                    break

                events = self._build_mini_transcript_events(all_responses)
                mini_text = self._mini_transcript_text(events)
                self._save_mini_transcript(
                    events,
                    "Post-exam follow-up (all questions)",
                    all_rubric_items,
                    index=fu_round + 1,
                )

                logger.info("Generating post-exam follow-up %d / %d…", fu_round + 1, post_exam_follow_ups)
                already_asked = [
                    fu.get("question", "")
                    for fu in exam_data.get("post_exam_follow_ups", [])
                    if isinstance(fu, dict) and fu.get("question")
                ]
                follow_up_q = llm_api.generate_follow_up(
                    system_prompt=sp,
                    question="Based on the questions so far.",
                    rubric_items=all_rubric_items,
                    missing_items=missing,
                    mini_transcript_text=mini_text,
                    lecture_material=lecture_material,
                    already_asked_follow_ups=already_asked,
                )
                if not follow_up_q:
                    break

                self._speak("I have a quick follow-up.")
                time.sleep(0.5)
                self._set_live_state(status="speaking", question=follow_up_q)
                self._speak(follow_up_q)
                time.sleep(0.5)

                fu_response = self.listen_for_response()
                exam_data.setdefault("post_exam_follow_ups", []).append(
                    {
                        "question": follow_up_q,
                        "response": fu_response,
                        "missing_items": list(missing),
                    }
                )
                self._set_live_state(
                    transcript_preview=(fu_response.get("text", "") or "")[:200],
                    status="thinking",
                )

        # Wrap up
        if self._stop_requested.is_set():
            exam_data["status"] = "stopped"
        else:
            exam_data["status"] = "completed"
        exam_data["end_time"] = datetime.now().isoformat()

        # Save all transcripts
        self._save_session_transcript(exam_id, exam_data)

        # Stop recording + mux
        if self.enable_vision:
            self.camera.stop_recording()
            self._stop_audio_and_mux()

        # Generate and save grading notes
        try:
            final_md_path = settings.SESSIONS_DIR / exam_id / "final_transcript.md"
            final_md = final_md_path.read_text(encoding="utf-8") if final_md_path.exists() else ""
            if final_md:
                logger.info("Generating grading notes with OpenAI…")
                notes = llm_api.generate_grading_notes(
                    system_prompt=self._system_prompt,
                    exam_config=exam_config,
                    final_transcript_md=final_md,
                )
                (settings.SESSIONS_DIR / exam_id / "grading_notes.md").write_text(
                    notes, encoding="utf-8"
                )
                logger.info("Grading notes saved.")
        except Exception as e:
            logger.warning("Could not generate grading notes: %s", e)

        logger.info("Exam complete. Session: %s → %s", exam_id, settings.SESSIONS_DIR / exam_id)
        self._set_live_state(status="done")
        return exam_data

    # ------------------------------------------------------------------ #
    #  Shutdown
    # ------------------------------------------------------------------ #

    def shutdown(self):
        logger.info("Shutting down proctor…")
        if self.enable_vision:
            self.camera.stop_recording()
            self._stop_audio_and_mux()
            self.camera.close()
