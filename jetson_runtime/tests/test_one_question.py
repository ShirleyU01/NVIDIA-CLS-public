#!/usr/bin/env python3
"""
Test one complete question + follow-up with the full V2 pipeline.

Usage:
    export OPENAI_API_KEY='sk-...'
    python3 tests/test_one_question.py
    python3 tests/test_one_question.py --no-vision
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from config import settings

QUESTION = "What is Big-O notation and why is it useful?"
RUBRIC_ITEMS = [
    "Definition: Big-O describes the upper bound / worst-case growth rate",
    "At least one concrete example (e.g. O(n), O(log n), O(n^2))",
    "Why it matters: compare algorithms, predict scaling",
]
SYSTEM_PROMPT = (
    "You are an oral exam proctor for a computer science course. "
    "The student is being assessed on algorithmic complexity. "
    "Be encouraging but rigorous. Do not provide hints."
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-vision", action="store_true")
    args = parser.parse_args()

    if not settings.OPENAI_API_KEY:
        print("❌  OPENAI_API_KEY not set.")
        sys.exit(1)

    enable_vision = not args.no_vision

    SEP = "=" * 65
    print(SEP)
    print("  SINGLE QUESTION TEST — jetson_runtime")
    print(f"  STT model : {settings.STT_MODEL}")
    print(f"  OpenAI    : {settings.OPENAI_MODEL}")
    print(f"  Vision    : {'ON' if enable_vision else 'OFF'}")
    print(f"  Sessions  : {settings.SESSIONS_DIR}")
    print(SEP)
    print()
    print("You have up to 60 seconds to answer.")
    print("Press Enter OR say 'I'm done' to finish early.")
    print()

    from proctor import OralExamProctor

    proctor = OralExamProctor(enable_vision=enable_vision)

    try:
        if enable_vision:
            proctor._ensure_session_folder()

        proctor._system_prompt = SYSTEM_PROMPT
        proctor._speak("Hello! Let's begin the test.")

        import time
        time.sleep(1)

        result = proctor.conduct_question(
            question=QUESTION,
            rubric_items=RUBRIC_ITEMS,
            system_prompt=SYSTEM_PROMPT,
            max_follow_ups=1,
        )

        # Save transcripts
        proctor.save_final_transcript(result)

        # Print summary
        print()
        print(SEP)
        print("  RESULT SUMMARY")
        print(SEP)
        print(f"  Question : {result['question']}")
        resp_text = result['responses'][0]['text'] if result.get('responses') else '(none)'
        print(f"  Answer   : {resp_text[:200]}{'...' if len(resp_text) > 200 else ''}")

        if result.get("initial_analysis", {}).get("items"):
            print()
            print("  Initial rubric analysis:")
            for item in result["initial_analysis"]["items"]:
                print(f"    [{item.get('status','?'):8s}] {item.get('item','?')}")

        if result.get("follow_ups"):
            fu = result["follow_ups"][0]
            print()
            print(f"  Follow-up: {fu['question']}")
            fu_text = fu["response"]["text"]
            print(f"  Answer   : {fu_text[:200]}{'...' if len(fu_text) > 200 else ''}")

        if result.get("final_analysis", {}).get("items"):
            print()
            print("  Final rubric analysis:")
            for item in result["final_analysis"]["items"]:
                print(f"    [{item.get('status','?'):8s}] {item.get('item','?')}")

        if proctor._session_id:
            session_dir = settings.SESSIONS_DIR / proctor._session_id
            print()
            print(f"  Session saved to: {session_dir}")
            for f in sorted(session_dir.rglob("*")):
                if f.is_file():
                    print(f"    {f.relative_to(session_dir)}")

        print(SEP)

    finally:
        proctor.shutdown()


if __name__ == "__main__":
    main()
