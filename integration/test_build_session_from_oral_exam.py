"""
Tests for the adapter that converts a jetson_runtime oral exam session folder
into a session JSON compatible with the evidence packet pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def test_build_session_from_oral_exam_minimal(tmp_path: Path) -> None:
    """
    Given a simple transcript.json + final_transcript.json, the adapter
    should produce a session JSON whose shape matches the fixtures:
    - session_id from transcript
    - recording_uri defaulting to the session directory path + '/'
    - one QA block per question
    - screenshots attached based on question_number in final_transcript events
    """
    from integration.build_session_from_oral_exam import build_session_from_oral_exam

    session_dir = tmp_path / "session_1"
    session_dir.mkdir()

    transcript = {
        "exam_id": "session_1",
        "session_id": "session_1",
        "questions": [
            {
                "question": "What is Big-O notation and why is it useful?",
                "rubric_items": [],
                "responses": [
                    {
                        "text": "Big-O notation is used to analyze algorithms.",
                        "duration": 5.0,
                        "segments": [],
                    }
                ],
                "follow_ups": [
                    {
                        "question": "Can you be more precise?",
                        "response_text": "It describes worst-case growth rate.",
                        "response_segments": [],
                    }
                ],
            }
        ],
    }

    final_transcript = {
        "exam_id": "session_1",
        "session_id": "session_1",
        "events": [
            {
                "t": 0.0,
                "type": "question",
                "question_number": 1,
                "follow_up": False,
                "text": "What is Big-O notation and why is it useful?",
            },
            {
                "t": 1.0,
                "type": "answer",
                "text": "Big-O notation is used to analyze algorithms.",
            },
            {
                "t": 3.5,
                "type": "screenshot",
                "path": "images/deixis_example.jpg",
                "trigger_word": "here",
            },
            {
                "t": 6.0,
                "type": "question",
                "question_number": 1,
                "follow_up": True,
                "text": "Can you be more precise?",
            },
            {
                "t": 7.0,
                "type": "answer",
                "text": "It describes worst-case growth rate.",
            },
        ],
    }

    _write_json(session_dir / "transcript.json", transcript)
    _write_json(session_dir / "final_transcript.json", final_transcript)

    session_json = build_session_from_oral_exam(session_dir)

    # Top-level fields
    assert session_json["session_id"] == "session_1"
    # Default recording_uri should be the session directory path with a trailing slash
    assert session_json["recording_uri"].endswith("session_1/")

    qa_blocks = session_json["qa_blocks"]
    assert len(qa_blocks) == 1
    block = qa_blocks[0]
    assert block["block_id"] == "Q1"
    assert "Big-O notation and why is it useful" in block["question"]

    # Student answer should concatenate the response and follow-up response text
    student_answer = block["student_answer"]
    assert "Big-O notation is used to analyze algorithms." in student_answer
    assert "It describes worst-case growth rate." in student_answer

    # Main response and follow-up responses are explicit for grading
    assert block["main_response"] == "Big-O notation is used to analyze algorithms."
    assert block["follow_up_responses"] == ["It describes worst-case growth rate."]

    # Screenshot from final_transcript should be attached to this block
    shots = block["screenshots"]
    assert len(shots) == 1
    assert shots[0]["timestamp"] == pytest.approx(3.5)
    assert shots[0]["image_id"] == "images/deixis_example.jpg"
    assert shots[0]["region"] is None

    # Actual follow-up questions asked during the exam (for evidence packet word-for-word display)
    assert "asked_followup_questions" in session_json
    assert session_json["asked_followup_questions"] == ["Can you be more precise?"]


def test_build_session_from_oral_exam_no_screenshots(tmp_path: Path) -> None:
    """
    When there are no screenshot events, the adapter should still build
    QA blocks with empty screenshots arrays.
    """
    from integration.build_session_from_oral_exam import build_session_from_oral_exam

    session_dir = tmp_path / "session_2"
    session_dir.mkdir()

    transcript = {
        "exam_id": "session_2",
        "session_id": "session_2",
        "questions": [
            {
                "question": "Explain Big-O notation.",
                "rubric_items": [],
                "responses": [
                    {"text": "It's about asymptotic growth.", "duration": 4.0, "segments": []}
                ],
                "follow_ups": [],
            }
        ],
    }

    final_transcript = {
        "exam_id": "session_2",
        "session_id": "session_2",
        "events": [
            {
                "t": 0.0,
                "type": "question",
                "question_number": 1,
                "follow_up": False,
                "text": "Explain Big-O notation.",
            },
            {
                "t": 1.0,
                "type": "answer",
                "text": "It's about asymptotic growth.",
            },
        ],
    }

    _write_json(session_dir / "transcript.json", transcript)
    _write_json(session_dir / "final_transcript.json", final_transcript)

    session_json = build_session_from_oral_exam(session_dir)

    qa_blocks = session_json["qa_blocks"]
    assert len(qa_blocks) == 1
    block = qa_blocks[0]
    assert block["block_id"] == "Q1"
    assert block["screenshots"] == []
    assert session_json.get("asked_followup_questions") == []


def test_build_session_from_oral_exam_includes_global_followups(tmp_path: Path) -> None:
    from integration.build_session_from_oral_exam import build_session_from_oral_exam

    session_dir = tmp_path / "session_global_fu"
    session_dir.mkdir()

    transcript = {
        "exam_id": "session_global_fu",
        "session_id": "session_global_fu",
        "questions": [
            {
                "question": "Main question?",
                "rubric_items": [],
                "responses": [
                    {"text": "Main answer.", "duration": 3.0, "segments": []}
                ],
                "follow_ups": [],
            }
        ],
        "post_exam_follow_ups": [
            {
                "question": "Global follow-up question?",
                "response_text": "Global follow-up answer.",
                "response_segments": [],
                "missing_items": ["Some rubric item"],
            }
        ],
    }

    final_transcript = {
        "exam_id": "session_global_fu",
        "session_id": "session_global_fu",
        "events": [
            {
                "t": 0.0,
                "type": "question",
                "question_number": 1,
                "follow_up": False,
                "text": "Main question?",
            },
            {"t": 1.0, "type": "answer", "text": "Main answer."},
            {
                "t": 5.0,
                "type": "question",
                "question_number": None,
                "follow_up": True,
                "follow_up_scope": "global",
                "text": "Global follow-up question?",
            },
            {"t": 6.0, "type": "answer", "text": "Global follow-up answer."},
            {
                "t": 6.4,
                "type": "screenshot",
                "path": "images/global_fu.jpg",
                "trigger_word": "this",
            },
        ],
    }

    _write_json(session_dir / "transcript.json", transcript)
    _write_json(session_dir / "final_transcript.json", final_transcript)

    session_json = build_session_from_oral_exam(session_dir)
    qa_blocks = session_json["qa_blocks"]
    assert len(qa_blocks) == 2

    global_block = qa_blocks[1]
    assert global_block["block_id"] == "GF1"
    assert global_block["question"] == "Global follow-up question?"
    assert global_block["student_answer"] == "Global follow-up answer."
    assert global_block["main_response"] == "Global follow-up answer."
    assert global_block["follow_up_responses"] == []
    assert len(global_block["screenshots"]) == 1
    assert global_block["screenshots"][0]["image_id"] == "images/global_fu.jpg"
    assert session_json["asked_followup_questions"] == ["Global follow-up question?"]

