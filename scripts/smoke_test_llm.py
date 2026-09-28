"""
Live smoke test: exercise the real OpenAI API with the configured model
(gpt-5.4-mini) and reasoning_effort=low, then validate that the
post-session student/teacher builders return well-formed v1 three-bucket
JSON.

Run from repo root:
    python scripts/smoke_test_llm.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jetson_runtime"))


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

from config import settings  # noqa: E402
from study_guide.feedback_aggregation import CaptureRecord  # noqa: E402
from study_guide.student_summary import build_study_student_feedback_multi  # noqa: E402
from study_guide.teacher_summary import build_study_teacher_summary_multi  # noqa: E402


def _openai_complete(system: str, user: str) -> str:
    """Mirror the adapter used inside jetson_backend._openai_complete."""
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL or None,
    )
    resp = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        reasoning_effort=settings.OPENAI_REASONING_EFFORT,
    )
    return (resp.choices[0].message.content or "").strip()


def _fake_captures() -> list[CaptureRecord]:
    return [
        CaptureRecord(
            index=1,
            image_filename="paper_1.jpg",
            feedback_json={
                "verdict": "Partially correct",
                "notes": "Wrote P(A|B)=P(B|A)P(A)/P(B) correctly but swapped numerator and denominator on substitution.",
            },
            feedback_md=(
                "- Bayes' rule stated correctly.\n"
                "- Arithmetic slip: 0.01 * 0.99 placed in denominator instead of numerator.\n"
            ),
            question_index=0,
        ),
        CaptureRecord(
            index=1,
            image_filename="paper_2.jpg",
            feedback_json={
                "verdict": "Mostly correct",
                "notes": "Identified iid assumption and set up MLE correctly; final derivative sign error.",
            },
            feedback_md=(
                "- Likelihood set up correctly.\n"
                "- Sign error when differentiating log-likelihood w.r.t. mu.\n"
            ),
            question_index=1,
        ),
    ]


def _questions() -> list[tuple[str, list[str]]]:
    return [
        (
            "Apply Bayes' rule to a disease-test scenario with base rate 1%.",
            [
                "State Bayes' rule",
                "Plug in base rate correctly",
                "Compute posterior probability",
            ],
        ),
        (
            "Derive the MLE for the mean of a Gaussian given N iid samples.",
            [
                "State likelihood",
                "Take log-likelihood",
                "Differentiate and solve",
            ],
        ),
    ]


def _check_list_of_str(obj, name: str) -> list[str]:
    errs = []
    if not isinstance(obj, list):
        errs.append(f"{name}: expected list, got {type(obj).__name__}")
        return errs
    for i, x in enumerate(obj):
        if not isinstance(x, str):
            errs.append(f"{name}[{i}]: expected str, got {type(x).__name__}")
        elif not x.strip():
            errs.append(f"{name}[{i}]: empty string")
    return errs


def validate_student(fb: dict) -> list[str]:
    errs = []
    for key in ("high_level_takeaways", "areas_to_improve", "next_steps"):
        if key not in fb:
            errs.append(f"missing key: {key}")
        else:
            errs.extend(_check_list_of_str(fb[key], key))
    # voice check: no "the student" references
    blob = json.dumps(fb).lower()
    if "the student" in blob:
        errs.append('voice check failed: contains "the student"')
    return errs


def validate_teacher(summary: dict) -> list[str]:
    errs = []
    if not isinstance(summary.get("summary"), str) or not summary["summary"].strip():
        errs.append("summary: expected non-empty str")
    for key in ("flags", "action_items"):
        if key not in summary:
            errs.append(f"missing key: {key}")
        else:
            errs.extend(_check_list_of_str(summary[key], key))
    return errs


def main() -> int:
    if not settings.OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY not set (check .env)", file=sys.stderr)
        return 2

    print(f"Model              = {settings.OPENAI_MODEL}")
    print(f"Reasoning effort   = {settings.OPENAI_REASONING_EFFORT}")
    print(f"Base URL           = {settings.OPENAI_BASE_URL or '(default)'}")
    print()

    captures = _fake_captures()
    questions = _questions()

    exit_code = 0

    print("== Student multi-question feedback ==")
    try:
        student = build_study_student_feedback_multi(
            questions=questions,
            captures=captures,
            llm_complete_fn=_openai_complete,
        )
    except Exception as e:
        print(f"  ERROR: exception during call: {e}")
        return 1
    print(json.dumps(student, indent=2))
    s_errs = validate_student(student)
    if s_errs:
        print("  VALIDATION ERRORS:")
        for e in s_errs:
            print(f"   - {e}")
        exit_code = 1
    else:
        print("  OK: three-bucket schema valid, second-person voice.")
    print()

    print("== Teacher multi-question summary ==")
    try:
        teacher = build_study_teacher_summary_multi(
            questions=questions,
            captures=captures,
            student_feedback=student,
            llm_complete_fn=_openai_complete,
        )
    except Exception as e:
        print(f"  ERROR: exception during call: {e}")
        return 1
    print(json.dumps(teacher, indent=2))
    t_errs = validate_teacher(teacher)
    if t_errs:
        print("  VALIDATION ERRORS:")
        for e in t_errs:
            print(f"   - {e}")
        exit_code = 1
    else:
        print("  OK: narrative summary + flags + action_items all present.")
    print()

    # Also sanity-check the Responses API path (AMA / lost/question) accepts
    # reasoning={"effort": ...} with this model.
    print("== Responses API (reasoning param acceptance) ==")
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL or None,
        )
        resp = client.responses.create(
            model=settings.OPENAI_MODEL,
            input=[{"role": "user", "content": [{"type": "input_text", "text": "Reply with exactly the word: PONG"}]}],
            reasoning={"effort": settings.OPENAI_REASONING_EFFORT},
        )
        out = (getattr(resp, "output_text", "") or "").strip()
        print(f"  reply: {out!r}")
        if not out:
            print("  WARNING: empty output_text")
            exit_code = 1
        else:
            print("  OK: Responses API accepts reasoning={'effort': 'low'}.")
    except Exception as e:
        print(f"  ERROR: {e}")
        exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
