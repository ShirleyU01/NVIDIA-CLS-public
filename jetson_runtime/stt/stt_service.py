"""
STT service — faster-whisper small.en

Improvements over V1:
  - small.en instead of base (significantly better accuracy)
  - English-only model (avoids multilingual detection overhead)
  - initial_prompt with domain vocabulary for technical terms
  - Generous VAD padding so first/last words aren't clipped
"""
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings

logger = logging.getLogger(__name__)


class STTService:
    def __init__(self):
        logger.info("Loading faster-whisper model: %s (device=%s, compute=%s)",
                    settings.STT_MODEL, settings.STT_DEVICE, settings.STT_COMPUTE_TYPE)
        from faster_whisper import WhisperModel
        self._model = WhisperModel(
            settings.STT_MODEL,
            device=settings.STT_DEVICE,
            compute_type=settings.STT_COMPUTE_TYPE,
        )
        logger.info("STT model loaded.")

    def transcribe(self, audio_path: str, initial_prompt: str = None) -> dict:
        """
        Transcribe audio file.

        Returns:
            {
                "text": str,                       # full stitched transcript
                "segments": [                      # word-level timing
                    {"start": float, "end": float, "text": str}, ...
                ],
                "transcription_time": float,       # seconds taken
            }
        """
        if not Path(audio_path).exists():
            logger.warning("Audio file not found: %s", audio_path)
            return {"text": "", "segments": [], "transcription_time": 0.0}

        prompt = initial_prompt if initial_prompt is not None else settings.STT_INITIAL_PROMPT

        t0 = time.time()
        segments_iter, info = self._model.transcribe(
            audio_path,
            language=settings.STT_MODEL_LANGUAGE,
            beam_size=settings.STT_BEAM_SIZE,
            initial_prompt=prompt,
            # Disable chaining context across segments — prevents one bad segment
            # from hallucinating into the next (e.g. "rhythms to R" compounding).
            condition_on_previous_text=False,
            # Skip segments where the model has low confidence there is speech.
            no_speech_threshold=0.6,
            # Suppress common filler/hallucination tokens (blank audio artefacts).
            suppress_blank=True,
            vad_filter=settings.STT_VAD_FILTER,
            vad_parameters={
                "speech_pad_ms": settings.STT_VAD_SPEECH_PAD_MS,
                "min_silence_duration_ms": settings.STT_VAD_MIN_SILENCE_MS,
            },
        )

        segments = []
        texts = []
        for seg in segments_iter:
            text = seg.text.strip()
            if text:
                segments.append({"start": seg.start, "end": seg.end, "text": text})
                texts.append(text)

        elapsed = time.time() - t0
        full_text = " ".join(texts)
        logger.info("Transcribed %.1fs audio in %.2fs: %d chars", info.duration, elapsed, len(full_text))
        return {"text": full_text, "segments": segments, "transcription_time": elapsed}


_instance: STTService = None


def get_stt_service() -> STTService:
    global _instance
    if _instance is None:
        _instance = STTService()
    return _instance
