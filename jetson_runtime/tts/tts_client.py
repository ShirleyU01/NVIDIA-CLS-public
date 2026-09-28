"""
Piper TTS client — V2

Improvements over V1:
  - paplay (PulseAudio) instead of aplay: proper device buffering, no first-syllable clipping.
  - Splits on sentence boundaries (. ! ?) so words are never cut mid-sentence.
  - Natural inter-sentence pause (a real short silence file).
  - Shorter TTS_MAX_CHUNK_CHARS so Piper never gets an overlong string.
"""
import hashlib
import logging
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Tiny silence generator (pure-Python WAV, no sox/ffmpeg dependency)
# --------------------------------------------------------------------------- #

def _make_silence_wav(duration_ms: int, path: str,
                      sample_rate: int = 22050, channels: int = 1):
    """Write a minimal WAV file of silence at the given path."""
    num_samples = int(sample_rate * duration_ms / 1000)
    pcm = b"\x00" * (num_samples * 2 * channels)   # 16-bit PCM
    data_size = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16,
        1,                                    # PCM
        channels,
        sample_rate,
        sample_rate * channels * 2,           # byte-rate
        channels * 2,                         # block-align
        16,                                   # bits-per-sample
        b"data", data_size,
    )
    Path(path).write_bytes(header + pcm)


# --------------------------------------------------------------------------- #
#  TTS client
# --------------------------------------------------------------------------- #

class TTSClient:
    def __init__(self):
        self._cache = settings.TTS_CACHE_DIR
        # Pre-generate silence clips: inter-sentence pause and leading pads.
        self._silence_path = str(self._cache / "_silence_200ms.wav")
        if not Path(self._silence_path).exists():
            _make_silence_wav(200, self._silence_path)
        leading_ms = int(getattr(settings, "TTS_LEADING_SILENCE_MS", 2200))
        self._leading_silence_path = str(self._cache / f"_silence_leading_{leading_ms}ms.wav")
        if not Path(self._leading_silence_path).exists():
            _make_silence_wav(leading_ms, self._leading_silence_path)
        chunk_ms = int(getattr(settings, "TTS_CHUNK_LEADING_SILENCE_MS", 400))
        self._chunk_leading_silence_path = str(self._cache / f"_silence_chunk_{chunk_ms}ms.wav")
        if not Path(self._chunk_leading_silence_path).exists():
            _make_silence_wav(chunk_ms, self._chunk_leading_silence_path)

    # ------------------------------------------------------------------ #
    #  Public
    # ------------------------------------------------------------------ #

    def speak(self, text: str):
        """Split text into natural sentences and speak each one."""
        sentences = self._split_sentences(text.strip())
        if not sentences:
            return
        for i, sentence in enumerate(sentences):
            if not sentence:
                continue
            # Pad before first chunk (long) and each later chunk (short) so paplay does not clip onset.
            self._play(self._leading_silence_path if i == 0 else self._chunk_leading_silence_path)
            wav = self._synthesize(sentence)
            if not wav:
                # Dev-friendly fallback (e.g. macOS hosts without Piper running).
                # On Jetson/Linux the primary path should be Piper -> paplay/aplay.
                self._fallback_speak(sentence)
                continue
            if i > 0:
                # Short pause between sentences for natural cadence
                self._play(self._silence_path)
            self._play(wav)

    # ------------------------------------------------------------------ #
    #  Sentence splitting
    # ------------------------------------------------------------------ #

    def _split_sentences(self, text: str) -> list:
        """
        Split on . ! ? boundaries.  If a resulting sentence is still over
        TTS_MAX_CHUNK_CHARS, split further on commas then on words.
        """
        import re
        text = " ".join(text.split())                        # normalise whitespace
        raw = re.split(r"(?<=[.!?])\s+", text)              # split on sentence end
        chunks = []
        for sent in raw:
            sent = sent.strip()
            if not sent:
                continue
            if len(sent) <= settings.TTS_MAX_CHUNK_CHARS:
                chunks.append(sent)
            else:
                # Try comma-splitting first
                parts = [p.strip() for p in sent.split(",") if p.strip()]
                buf = ""
                for part in parts:
                    candidate = (buf + ", " + part) if buf else part
                    if len(candidate) <= settings.TTS_MAX_CHUNK_CHARS:
                        buf = candidate
                    else:
                        if buf:
                            chunks.append(buf)
                        buf = part
                if buf:
                    chunks.append(buf)
        return [c for c in chunks if c]

    # ------------------------------------------------------------------ #
    #  Synthesis + cache
    # ------------------------------------------------------------------ #

    def _synthesize(self, text: str) -> str:
        """Synthesize one sentence → cached WAV path (or '' on failure)."""
        pad = getattr(settings, "TTS_TEXT_LEADING_PAD", "  ") or ""
        spoken = f"{pad}{text.strip()}"
        key = hashlib.md5(f"{settings.TTS_VOICE}:{spoken}".encode()).hexdigest()
        cached = self._cache / f"{key}.wav"
        if cached.exists():
            return str(cached)
        try:
            resp = requests.post(
                settings.TTS_URL,
                json={"text": spoken, "voice": settings.TTS_VOICE},
                timeout=20,
            )
            if resp.status_code == 200:
                cached.write_bytes(resp.content)
                return str(cached)
            logger.error("Piper TTS HTTP %s for: %s", resp.status_code, text[:60])
        except requests.exceptions.Timeout:
            logger.error("Piper TTS timed out — is it running?  ./start_tts.sh")
        except Exception as e:
            logger.error("Piper TTS error: %s", e)
        return ""

    # ------------------------------------------------------------------ #
    #  Playback
    # ------------------------------------------------------------------ #

    def _play(self, wav_path: str):
        """
        Play WAV file.  Prefer paplay (PulseAudio) — it buffers properly so the
        first syllable is never cut off.  Falls back to aplay if paplay is absent.
        """
        try:
            result = subprocess.run(
                ["paplay", wav_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                return
        except FileNotFoundError:
            pass  # paplay not installed — fall through to aplay

        # aplay fallback
        try:
            subprocess.run(["aplay", "-q", wav_path], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning("Audio playback failed: %s", e)

        # macOS fallback
        if sys.platform == "darwin":
            try:
                subprocess.run(
                    ["afplay", wav_path],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                logger.warning("Audio playback failed (afplay): %s", e)

    def _fallback_speak(self, text: str) -> None:
        """
        Fallback path when Piper is unavailable or returns non-200.
        Intended primarily for local UI development on macOS.
        """
        if sys.platform != "darwin":
            return
        try:
            subprocess.run(
                ["say", text],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.warning("Fallback TTS failed (say): %s", e)


_instance: TTSClient = None


def get_tts_client() -> TTSClient:
    global _instance
    if _instance is None:
        _instance = TTSClient()
    return _instance
