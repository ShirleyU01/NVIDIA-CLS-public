#!/usr/bin/env python3
"""
Test OpenAI connection + all four API calls with dummy data.
Run: OPENAI_API_KEY=xxx python3 tests/test_openai.py
"""
import sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from config import settings
from cloud_llm import openai_client as llm

if not settings.OPENAI_API_KEY:
    print("❌  OPENAI_API_KEY not set. Export it or put it in jetson_runtime/.env")
    sys.exit(1)

SEP = "=" * 60
SYSTEM_PROMPT = "You are a concise oral exam proctor for computer science."
QUESTION = "What is Big-O notation?"
RUBRIC = ["Definition of growth rate", "At least one example", "Why it matters"]
TRANSCRIPT = "Big-O notation tells us how fast an algorithm grows, like O of n squared."

print(SEP)
print("  OpenAI API Test")
print(f"  Model: {settings.OPENAI_MODEL}")
print(SEP)

print("\n[1/4] generate_question...")
q = llm.generate_question(SYSTEM_PROMPT, QUESTION, RUBRIC)
print(f"  → {q}")

print("\n[2/4] analyze_response...")
analysis = llm.analyze_response(SYSTEM_PROMPT, QUESTION, RUBRIC, TRANSCRIPT)
for item in analysis.get("items", []):
    print(f"  {item.get('status','?'):8s}  {item.get('item','?')}")

print("\n[3/4] generate_follow_up...")
missing = [i["item"] for i in analysis.get("items", []) if i.get("status") == "Missing"]
if missing:
    fu = llm.generate_follow_up(SYSTEM_PROMPT, QUESTION, RUBRIC, missing, TRANSCRIPT)
    print(f"  → {fu}")
else:
    print("  (all items met — no follow-up needed)")

print("\n[4/4] generate_grading_notes...")
notes = llm.generate_grading_notes(
    SYSTEM_PROMPT,
    {"exam_id": "test"},
    f"| 0:00 | EXAMINER | {QUESTION} |\n| 0:05 | STUDENT | {TRANSCRIPT} |",
)
print(f"  → {notes[:200]}...")

print(SEP)
print("✅ OpenAI API is working.")
print(SEP)
