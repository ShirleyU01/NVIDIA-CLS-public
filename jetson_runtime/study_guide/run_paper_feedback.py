#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")
except Exception:
    pass

from config import settings
from session_manager import get_next_session_id
from study_guide.paper_capture import capture_paper_image
from study_guide.vision_feedback import request_paper_feedback


def _load_question(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Study guide: paper → camera → feedback")
    parser.add_argument(
        "--question",
        required=True,
        help="Path to a study guide question JSON (see study_guide/example_questions/)",
    )
    parser.add_argument("--countdown", type=int, default=5, help="Seconds before photo capture")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--model", help="Override OpenAI model for vision feedback")
    parser.add_argument(
        "--camera-device",
        help="Override camera device path (default: config/settings.py CAMERA_DEVICE)",
    )
    parser.add_argument(
        "--no-input",
        action="store_true",
        help="Do not prompt for Enter before capture (useful for non-interactive runs)",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Capture image and exit (no OpenAI call).",
    )
    args = parser.parse_args()

    if not settings.OPENAI_API_KEY and not args.skip_llm:
        print("Error: OPENAI_API_KEY is not set.")
        print("  Export it: export OPENAI_API_KEY='sk-...'")
        print("  Or put it in jetson_runtime/.env as: OPENAI_API_KEY=sk-...")
        return 2

    q_path = Path(args.question)
    if not q_path.exists():
        print(f"Error: question config not found: {q_path}")
        return 2

    q = _load_question(q_path)
    question_text = (q.get("question_text") or "").strip()
    rubric_items = q.get("rubric_items") or []
    title = q.get("title") or q.get("question_id") or q_path.name

    if not question_text:
        print("Error: question_text missing/empty in question JSON")
        return 2
    if not isinstance(rubric_items, list) or not all(isinstance(x, str) for x in rubric_items):
        print("Error: rubric_items must be a list of strings")
        return 2

    session_id = get_next_session_id()
    session_dir = settings.SESSIONS_DIR / session_id / "paper"
    session_dir.mkdir(parents=True, exist_ok=True)
    camera_device = args.camera_device or settings.CAMERA_DEVICE

    print("=" * 70)
    print("  STUDY GUIDE — PAPER FEEDBACK")
    print(f"  Session:  {session_id}")
    print(f"  Title:    {title}")
    print(f"  Camera:   {camera_device}")
    print(f"  Output:   {session_dir}")
    print("=" * 70)
    print()
    print("Problem:")
    print(question_text)
    print()
    print("Instructions:")
    print("- Work on paper.")
    print("- Hold the paper steady in front of the camera (fill the frame).")
    print("- Ensure lighting is bright and avoid glare/shadows.")
    print()
    if not args.no_input:
        input("Press Enter when you're ready to capture a photo… ")

    for i in range(int(args.countdown), 0, -1):
        print(f"Capturing in {i}…")
        time.sleep(1)

    img_path = session_dir / f"paper_{int(time.time())}.jpg"
    try:
        captured = capture_paper_image(
            camera_device=camera_device,
            output_path=img_path,
            width=int(args.width),
            height=int(args.height),
        )
    except Exception as e:
        print(f"Error: capture failed: {e}")
        print()
        print("Troubleshooting:")
        print("- Verify the camera is plugged in and appears under /dev (e.g. /dev/video0).")
        print("- Try: python3 tests/test_camera.py (oral exam camera test).")
        print("- Or pass the correct device via: --camera-device /dev/videoX")
        return 1

    print(f"Captured: {captured}")

    if args.skip_llm:
        print()
        print("Skipping LLM feedback (--skip-llm).")
        print("Saved:")
        print(f"- {captured}")
        return 0

    print()
    print("Requesting feedback (vision)…")

    feedback = request_paper_feedback(
        question_text=question_text,
        rubric_items=rubric_items,
        image_paths=[captured],
        model=args.model,
    )

    (session_dir / "paper_feedback.json").write_text(
        json.dumps(feedback.json, indent=2), encoding="utf-8"
    )
    (session_dir / "paper_feedback.md").write_text(feedback.md + "\n", encoding="utf-8")

    print()
    print("=" * 70)
    print("FEEDBACK (markdown)")
    print("=" * 70)
    print(feedback.md)
    print("=" * 70)
    print()
    print("Saved:")
    print(f"- {session_dir / 'paper_feedback.json'}")
    print(f"- {session_dir / 'paper_feedback.md'}")
    print(f"- {captured}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

