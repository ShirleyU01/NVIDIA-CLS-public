"""Tests for AMA tutor prompt guardrails."""

from study_guide.ama_prompt import build_study_ama_prompt


def test_prompt_requires_staying_on_session_topic() -> None:
    prompt = build_study_ama_prompt(context="## Session overview\n- id: x", chat_block="")
    lower = prompt.lower()
    assert "unrelated" in lower or "off-topic" in lower or "outside this study session" in lower
    assert "recipe" in lower or "recipes" in lower


def test_prompt_requires_hints_before_full_answers() -> None:
    prompt = build_study_ama_prompt(context="## Session", chat_block="**Student:** hi")
    lower = prompt.lower()
    assert "hint" in lower
    assert "explicit" in lower
    assert "final" in lower or "complete solution" in lower
