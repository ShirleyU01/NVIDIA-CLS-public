"""
Tests for the evidence packet pipeline (load, normalize, validate, assemble).
Uses a mock LLM that returns valid JSON so no API key is required.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


def _mock_llm_returning_valid_packet(criterion_id: str, max_score: int):
    """Return a valid per-criterion JSON string for the given criterion."""
    payload = {
        "criterion_id": criterion_id,
        "score": 1,
        "score_rationale_anchor": "1",
        "llm_confidence": 0.8,
        "evidence": [
            {
                "type": "transcript_quote",
                "quote": "prior",
                "t0": 12.3,
                "t1": 12.3,
                "why_it_supports": "Mentions prior.",
            }
        ],
        "missing_evidence": [],
        "suggested_followup_question": "Can you give an example?",
        "flags": [],
    }
    if max_score == 1:
        payload["score"] = 1
        payload["score_rationale_anchor"] = "1"
    return json.dumps(payload)


def test_load_rubric_and_session():
    from integration.evidence_packet import load_rubric, load_session

    base = Path(__file__).resolve().parent  # integration/
    rubric_path = base / "fixtures" / "rubric_bayes_oral_v1.json"
    session_path = base / "fixtures" / "session_mock_001.json"
    assert rubric_path.exists(), f"Fixture missing: {rubric_path}"
    assert session_path.exists(), f"Fixture missing: {session_path}"

    rubric = load_rubric(str(rubric_path))
    assert rubric["rubric_id"] == "bayes_oral_v1"
    assert len(rubric["criteria"]) == 4
    assert rubric["criteria"][0]["max"] == 2
    assert rubric["criteria"][3]["max"] == 1

    session = load_session(str(session_path))
    assert session["session_id"] == "sess_mock_001"
    assert len(session["qa_blocks"]) == 2
    assert session["qa_blocks"][0]["block_id"] == "Q1"
    assert len(session["qa_blocks"][0]["screenshots"]) == 2


def test_normalize_blocks():
    from integration.evidence_packet import load_session, normalize_blocks

    base = Path(__file__).resolve().parent  # integration/
    session = load_session(str(base / "fixtures" / "session_mock_001.json"))
    session_id, recording_uri, blocks = normalize_blocks(session)
    assert session_id == "sess_mock_001"
    assert recording_uri == "sessions/sess_mock_001/"
    assert len(blocks) == 2
    assert blocks[0].block_id == "Q1"
    assert "prior" in blocks[0].student_answer
    assert len(blocks[0].screenshots) == 2
    assert blocks[0].screenshots[0].timestamp == 12.3
    assert blocks[1].screenshots == []


def test_validate_packet_item():
    from integration.evidence_packet import normalize_blocks, load_session, validate_packet_item
    from integration.evidence_packet.models import QABlock, Screenshot

    base = Path(__file__).resolve().parent  # integration/
    session = load_session(str(base / "fixtures" / "session_mock_001.json"))
    _, _, blocks = normalize_blocks(session)

    # Valid: quote in text, timestamp in screenshots
    item = {
        "score": 1,
        "evidence": [
            {"type": "transcript_quote", "quote": "prior", "t0": 12.3, "t1": 12.3}
        ],
        "llm_confidence": 0.8,
    }
    flags = validate_packet_item(item, blocks)
    assert "invalid_quote_not_found_in_answers" not in flags
    assert "invalid_timestamp_not_in_screenshots" not in flags

    # Invalid quote
    item_bad_quote = {
        "score": 1,
        "evidence": [
            {"type": "transcript_quote", "quote": "invented text", "t0": None, "t1": None}
        ],
        "llm_confidence": 0.8,
    }
    flags_bad = validate_packet_item(item_bad_quote, blocks)
    assert "invalid_quote_not_found_in_answers" in flags_bad

    # Score without evidence
    item_no_ev = {"score": 1, "evidence": [], "llm_confidence": 0.8}
    flags_no_ev = validate_packet_item(item_no_ev, blocks)
    assert "score_without_evidence" in flags_no_ev


def test_run_evidence_packet_with_mock_llm():
    from integration.evidence_packet import run_evidence_packet

    base = Path(__file__).resolve().parent  # integration/
    rubric_path = base / "fixtures" / "rubric_bayes_oral_v1.json"
    session_path = base / "fixtures" / "session_mock_001.json"

    def mock_llm(system_prompt: str, user_prompt: str) -> str:
        # Return valid JSON: quote from session_mock_001 Q1, timestamp 12.3 from Q1 screenshots
        cid = "C1"
        if "criterion_id: C2" in user_prompt:
            cid = "C2"
        elif "criterion_id: C3" in user_prompt:
            cid = "C3"
        elif "criterion_id: C4" in user_prompt:
            cid = "C4"
        c_max = 2 if cid != "C4" else 1
        return json.dumps({
            "criterion_id": cid,
            "score": 1,
            "score_rationale_anchor": "1",
            "llm_confidence": 0.7,
            "evidence": [
                {
                    "type": "transcript_quote",
                    "quote": "The prior is our belief about the parameter",
                    "t0": 12.3,
                    "t1": 12.3,
                    "why_it_supports": "Defines prior.",
                }
            ],
            "missing_evidence": [],
            "suggested_followup_question": "Can you give an example?",
            "flags": [],
        })

    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "evidence_packet.json"
        packet = run_evidence_packet(
            str(rubric_path), str(session_path), str(out_path), llm_complete_fn=mock_llm
        )
        assert packet["session_id"] == "sess_mock_001"
        assert packet["rubric_id"] == "bayes_oral_v1"
        assert "total_score" in packet
        assert "max_score" in packet
        assert packet["max_score"] == 2 + 2 + 2 + 0.5  # C1–C3 max 2, C4 max 1, weight 0.5
        assert len(packet["criteria"]) == 4
        assert out_path.exists()
        with open(out_path) as f:
            disk = json.load(f)
        assert disk["session_id"] == packet["session_id"]
