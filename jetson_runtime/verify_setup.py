#!/usr/bin/env python3
"""
Verify all V2 components are ready before running an exam.
Run: python3 verify_setup.py
"""
import sys
import os
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from config import settings

SEP = "━" * 55
PASS = "  ✅"
WARN = "  ⚠️ "
FAIL = "  ❌"
results = []

def check(label, ok, detail="", warn=False):
    if ok:
        print(f"{PASS}  {label}")
    elif warn:
        print(f"{WARN}  {label}  {detail}")
    else:
        print(f"{FAIL}  {label}  {detail}")
    results.append(ok or warn)

print(SEP)
print("  jetson_runtime Setup Verification")
print(SEP)
print()

# 1. Sessions dir
print("[1/6] Storage")
check("SSD sessions dir writable", settings.SESSIONS_DIR.exists() and os.access(settings.SESSIONS_DIR, os.W_OK),
      f"→ {settings.SESSIONS_DIR}")
print(f"       Using: {settings.SESSIONS_DIR}")

# 2. STT
print("\n[2/6] STT (faster-whisper)")
try:
    from stt.stt_service import get_stt_service
    stt = get_stt_service()
    check(f"Model '{settings.STT_MODEL}' loaded", True)
except Exception as e:
    check(f"Model '{settings.STT_MODEL}'", False, str(e))

# 3. TTS
print("\n[3/6] TTS (Piper)")
try:
    import requests
    r = requests.post(settings.TTS_URL, json={"text": "test"}, timeout=5)
    check(f"Piper TTS at {settings.TTS_URL}", r.status_code == 200)
except Exception as e:
    check(f"Piper TTS at {settings.TTS_URL}", False,
          "→ run: ./start_tts.sh", warn=True)

# 4. Camera
print("\n[4/6] Camera")
cam_ok = Path(settings.CAMERA_DEVICE).exists()
check(f"Camera device {settings.CAMERA_DEVICE}", cam_ok,
      "→ check USB camera is plugged in", warn=not cam_ok)
if cam_ok:
    try:
        from vlm.camera import get_camera
        cam = get_camera()
        cam.open()
        res = cam.capture_frame("/tmp/v2_verify_frame.jpg")
        check("Camera capture frame", bool(res))
        cam.close()
    except Exception as e:
        check("Camera capture frame", False, str(e), warn=True)

# 5. OpenAI
print("\n[5/6] OpenAI API")
key = settings.OPENAI_API_KEY
if not key:
    check("OPENAI_API_KEY set", False,
          "→ export OPENAI_API_KEY='sk-...' or add to jetson_runtime/.env")
else:
    check("OPENAI_API_KEY set", True, f"(ends …{key[-4:]})")
    try:
        from cloud_llm import openai_client as llm
        result = llm._chat([{"role": "user", "content": "Say 'ok' in one word."}], max_tokens=5)
        check(f"OpenAI {settings.OPENAI_MODEL} call", bool(result))
    except Exception as e:
        check(f"OpenAI {settings.OPENAI_MODEL} call", False, str(e))

# 6. ffmpeg (for video mux)
print("\n[6/6] ffmpeg (video muxing)")
try:
    subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    check("ffmpeg available", True)
except Exception:
    check("ffmpeg available", False,
          "→ sudo apt install ffmpeg", warn=True)

# Summary
print()
print(SEP)
passed = sum(1 for r in results if r)
total = len(results)
if all(results):
    print(f"  ✅ All {total} checks passed — ready to run an exam!")
    print()
    print("  Run: python3 run_exam.py --exam exams/example_exam.json")
else:
    print(f"  {passed}/{total} checks passed — fix issues above before running.")
print(SEP)
