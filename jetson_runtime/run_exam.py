#!/usr/bin/env python3
"""
jetson_runtime — Run an oral exam from a JSON config file.

Usage:
    export OPENAI_API_KEY='sk-...'
    python3 run_exam.py --exam exams/example_exam.json
    python3 run_exam.py --exam exams/example_exam.json --no-vision
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from config import settings

def main():
    parser = argparse.ArgumentParser(description="AI Oral Exam Proctor V2")
    parser.add_argument("--exam", required=True, help="Path to exam JSON config file")
    parser.add_argument("--no-vision", action="store_true", help="Disable camera/screenshots")
    parser.add_argument("--session-id", help="Override session ID (default: auto)")
    args = parser.parse_args()

    exam_path = Path(args.exam)
    if not exam_path.exists():
        print(f"Error: exam config not found: {exam_path}")
        sys.exit(1)

    if not settings.OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY is not set.")
        print("  Export it: export OPENAI_API_KEY='sk-...'")
        print("  Or put it in jetson_runtime/.env as: OPENAI_API_KEY=sk-...")
        sys.exit(1)

    exam_config = json.loads(exam_path.read_text(encoding="utf-8"))
    if args.session_id:
        exam_config["exam_id"] = args.session_id

    enable_vision = not args.no_vision

    print("=" * 70)
    print(f"  Oral Exam: {exam_config.get('subject', exam_config.get('exam_id', ''))}")
    print(f"  Questions: {len(exam_config.get('questions', []))}")
    print(f"  Vision:    {'ON' if enable_vision else 'OFF'}")
    print(f"  STT model: {settings.STT_MODEL}")
    print(f"  OpenAI:    {settings.OPENAI_MODEL}")
    print(f"  Sessions:  {settings.SESSIONS_DIR}")
    print("=" * 70)
    print()

    from proctor import OralExamProctor

    proctor = OralExamProctor(enable_vision=enable_vision)
    try:
        exam_data = proctor.conduct_exam(exam_config)
    finally:
        proctor.shutdown()

    session_dir = settings.SESSIONS_DIR / exam_data["exam_id"]
    print()
    print("=" * 70)
    print("  EXAM COMPLETE")
    print(f"  Session folder: {session_dir}")
    print("  Files saved:")
    for f in sorted(session_dir.glob("*")):
        if f.is_file():
            size = f.stat().st_size
            print(f"    {f.name:30s}  ({size:,} bytes)")
    print("=" * 70)


if __name__ == "__main__":
    main()
