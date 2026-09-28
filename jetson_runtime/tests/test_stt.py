#!/usr/bin/env python3
"""
Test STT accuracy: records 10 seconds of speech and prints the transcript.
Run: python3 tests/test_stt.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stt.stt_service import get_stt_service
from stt.audio_capture import get_audio_capture
from config import settings

SEP = "=" * 60

print(SEP)
print(f"  STT TEST — model: {settings.STT_MODEL} ({settings.STT_MODEL_LANGUAGE})")
print(SEP)
print(f"\nLoading model (first load takes ~10s)...")

stt = get_stt_service()
audio = get_audio_capture()

print("\nSpeak now for 10 seconds (say something with technical terms)...")
print("  e.g. 'Big-O notation describes the worst case complexity of an algorithm.'")
print("  Recording starts in 2 seconds...")
time.sleep(2)
print("  RECORDING...", flush=True)

wav_path = audio.record(10)
print("  Done. Transcribing...", flush=True)

result = stt.transcribe(wav_path)

print(SEP)
print("  TRANSCRIPT:")
print(f"  '{result['text']}'")
print(SEP)
print(f"  Segments: {len(result['segments'])}")
for seg in result["segments"]:
    print(f"    [{seg['start']:.2f}s–{seg['end']:.2f}s] {seg['text']}")
print(f"  Transcription time: {result['transcription_time']:.2f}s")
print(SEP)

import os
try:
    os.unlink(wav_path)
except Exception:
    pass
