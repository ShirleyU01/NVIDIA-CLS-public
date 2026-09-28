"""Tests for student-facing markdown cleanup in ``vision_feedback``."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_jetson_runtime = _HERE.parents[2]
if str(_jetson_runtime) not in sys.path:
    sys.path.insert(0, str(_jetson_runtime))

from study_guide.vision_feedback import (  # noqa: E402
    _extract_json_and_markdown,
    sanitize_student_feedback_markdown,
)


def test_sanitize_strips_json_fences():
    md = """## Student feedback

```json
{"summary": "x"}
```

You did well on part (a).
"""
    out = sanitize_student_feedback_markdown(md)
    assert "```" not in out
    assert "You did well" in out


def test_sanitize_strips_leading_raw_json_blob():
    blob = json.dumps({"summary": "internal", "correctness": "Partially correct"})
    md = f"""{blob}

## Student feedback

Great job — nice partial solution.
"""
    out = sanitize_student_feedback_markdown(md)
    assert "internal" not in out
    assert "Great job" in out
    assert out.startswith("##")


def test_sanitize_strips_json_between_heading_and_prose():
    blob = json.dumps(
        {
            "summary": "internal",
            "rubric": [],
            "correctness": "Correct",
            "key_mistakes": [],
            "next_steps": [],
            "clarifying_questions": [],
        }
    )
    md = f"""## Student feedback

{blob}

Excellent — your factorial notation is exactly right.
"""
    out = sanitize_student_feedback_markdown(md)
    assert "internal" not in out
    assert "Excellent" in out
    assert out.startswith("## Student feedback")


def test_sanitize_prefers_student_feedback_section_when_json_precedes_heading():
    blob = json.dumps({"summary": "hidden", "correctness": "Correct"})
    md = f"""{blob}

## Student feedback

Great job — keep going.
"""
    out = sanitize_student_feedback_markdown(md)
    assert "hidden" not in out
    assert out.startswith("## Student feedback")
    assert "Great job" in out


def test_sanitize_strips_generic_fence_without_json_language_tag():
    md = """## Student feedback

```
{"summary": "x", "correctness": "Partially correct", "rubric": []}
```

Nice work — almost there.
"""
    out = sanitize_student_feedback_markdown(md)
    assert "{" not in out or "Nice work" in out
    assert "Nice work" in out
    assert "```" not in out


def test_extract_then_sanitize_model_leaked_fence_in_markdown():
    raw = """{"summary": "s", "rubric": [], "correctness": "Correct", "key_mistakes": [], "next_steps": [], "clarifying_questions": []}

## Student feedback

```json
{"oops": true}
```

Excellent — all set.
"""
    parsed, md = _extract_json_and_markdown(raw)
    assert parsed.get("correctness") == "Correct"
    cleaned = sanitize_student_feedback_markdown(md)
    assert "```" not in cleaned
    assert "Excellent" in cleaned
