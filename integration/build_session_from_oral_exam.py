"""
Adapter to convert a jetson_runtime oral exam session folder into a
`session_mock`-style JSON suitable for the evidence packet pipeline.

Input:  jetson_runtime/sessions/<session_id>/
  - transcript.json
  - final_transcript.json
  - images/*.jpg (referenced by final_transcript events)

Output JSON shape (matches integration/fixtures/session_mock_*.json):
{
  "session_id": "...",
  "recording_uri": "path-or-uri-to-session-or-recording",
  "qa_blocks": [
    {
      "block_id": "Q1",
      "question": "Question text",
      "student_answer": "Full concatenated student answer for this block",
      "screenshots": [
        {
          "timestamp": 12.3,
          "image_id": "images/deixis_....jpg",
          "region": null
        }
      ]
    },
    ...
  ]
}
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _collect_screenshots_by_block(
    final_transcript: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Walk the flattened events timeline and assign screenshot events to the
    active logical block:
    - Base question blocks: Q1, Q2, ...
    - Per-question follow-ups are folded into the same base Qn block.
    - Global post-exam follow-ups are tracked as GF1, GF2, ...

    Heuristic:
    - Maintain current_qnum based on `question` events.
    - A non-follow-up question (`follow_up` is false) sets the base question
      number for a block.
    - A follow-up question for the same question_number is treated as part
      of the same block.
    - Any screenshot that occurs while current_qnum is set is associated
      with that question_number.
    """
    screenshots: Dict[str, List[Dict[str, Any]]] = {}
    current_block: Optional[str] = None
    global_followup_idx = 0

    for ev in final_transcript.get("events", []):
        ev_type = ev.get("type")
        if ev_type == "question":
            qnum = ev.get("question_number")
            is_follow_up = bool(ev.get("follow_up", False))
            follow_up_scope = str(ev.get("follow_up_scope", "") or "").strip().lower()

            # Non-follow-up question starts a new base block.
            if not is_follow_up:
                current_block = f"Q{int(qnum)}" if qnum is not None else None
            # Global post-exam follow-up gets its own block (GF1, GF2, ...).
            elif follow_up_scope == "global":
                global_followup_idx += 1
                current_block = f"GF{global_followup_idx}"
            # Per-question follow-up remains within the existing base Qn block.
            elif qnum is not None:
                current_block = f"Q{int(qnum)}"

        elif ev_type == "screenshot" and current_block is not None:
            t = float(ev.get("t", 0.0))
            path = str(ev.get("path", ""))
            # Region information is not available in the oral exam transcripts
            # today, so we leave it as None (matches fixtures that allow null).
            shot = {
                "timestamp": t,
                "image_id": path,
                "region": None,
            }
            screenshots.setdefault(current_block, []).append(shot)

    return screenshots


def build_session_from_oral_exam(
    session_dir: Path,
    *,
    recording_uri: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a normalized session JSON for the evidence packet pipeline from
    a single oral exam session folder.

    - `session_id` is taken from transcript.json (falls back to folder name).
    - `recording_uri` defaults to the session directory path (with a trailing
      slash), mirroring the fixtures, unless explicitly provided.
    - One QA block is produced per question entry in transcript.json.
      Follow-up questions and answers are folded into the same block's
      `student_answer` string.
    - Screenshots are inferred from final_transcript.json events and attached
      to the corresponding question via question_number.
    """
    session_dir = session_dir.resolve()
    transcript_path = session_dir / "transcript.json"
    final_transcript_path = session_dir / "final_transcript.json"

    if not transcript_path.is_file():
        raise FileNotFoundError(f"Missing transcript.json in {session_dir}")
    if not final_transcript_path.is_file():
        raise FileNotFoundError(f"Missing final_transcript.json in {session_dir}")

    transcript = _load_json(transcript_path)
    final_transcript = _load_json(final_transcript_path)

    session_id = str(transcript.get("session_id") or transcript.get("exam_id") or session_dir.name)

    # If the proctor saved exam_config (e.g. with lecture_material), include it for the evidence packet
    lecture_material = ""
    exam_config_path = session_dir / "exam_config.json"
    if exam_config_path.is_file():
        try:
            exam_config = _load_json(exam_config_path)
            lecture_material = str(exam_config.get("lecture_material") or "").strip()
        except Exception:
            pass

    if recording_uri is None:
        # Use a directory-style URI similar to the fixtures.
        # Example: "jetson_runtime/sessions/session_1/"
        recording_uri = session_dir.as_posix() + "/"

    screenshots_by_block = _collect_screenshots_by_block(final_transcript)

    qa_blocks: List[Dict[str, Any]] = []
    questions = transcript.get("questions", [])
    for idx, q in enumerate(questions):
        qnum = idx + 1
        block_id = f"Q{qnum}"

        question_text = str(q.get("question", ""))

        # Concatenate all student answers for this question, including
        # responses and follow-up responses, in chronological order.
        answer_chunks: List[str] = []
        for resp in q.get("responses", []):
            text = str(resp.get("text", "")).strip()
            if text:
                answer_chunks.append(text)
        for fu in q.get("follow_ups", []):
            text = str(fu.get("response_text", "")).strip()
            if text:
                answer_chunks.append(text)

        main_response = ""
        follow_up_responses: List[str] = []
        if answer_chunks:
            main_response = answer_chunks[0]
            follow_up_responses = answer_chunks[1:]

        student_answer = " ".join(answer_chunks).strip()

        shots = screenshots_by_block.get(f"Q{qnum}", [])

        qa_blocks.append(
            {
                "block_id": block_id,
                "question": question_text,
                "student_answer": student_answer,
                "main_response": main_response,
                "follow_up_responses": follow_up_responses,
                "screenshots": shots,
            }
        )

    # Optional: post-exam follow-ups are stored separately so they don't
    # contaminate the last base-question block.
    post_exam_followups = transcript.get("post_exam_follow_ups") or []
    for idx, fu in enumerate(post_exam_followups, start=1):
        qtext = str(fu.get("question", "")).strip()
        rtext = str(fu.get("response_text", "")).strip()
        if not qtext and not rtext:
            continue
        qa_blocks.append(
            {
                "block_id": f"GF{idx}",
                "question": qtext or f"Post-exam follow-up {idx}",
                "student_answer": rtext,
                "main_response": rtext,
                "follow_up_responses": [],
                "screenshots": screenshots_by_block.get(f"GF{idx}", []),
            }
        )

    # Flatten all follow-up questions actually asked during the exam (in order),
    # so the evidence packet can show them word-for-word instead of LLM-generated suggestions.
    asked_followup_questions: List[str] = []
    for q in questions:
        for fu in q.get("follow_ups", []):
            qtext = str(fu.get("question", "")).strip()
            if qtext:
                asked_followup_questions.append(qtext)
    for fu in post_exam_followups:
        qtext = str(fu.get("question", "")).strip()
        if qtext:
            asked_followup_questions.append(qtext)

    return {
        "session_id": session_id,
        "recording_uri": recording_uri,
        "qa_blocks": qa_blocks,
        "asked_followup_questions": asked_followup_questions,
        "lecture_material": lecture_material,
    }


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a jetson_runtime oral exam session folder into a "
            "session JSON compatible with the evidence packet pipeline."
        )
    )
    parser.add_argument(
        "--session-dir",
        required=True,
        help="Path to a jetson_runtime/sessions/<session_id> directory",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output path for the normalized session JSON",
    )
    parser.add_argument(
        "--recording-uri",
        default=None,
        help=(
            "Optional recording URI to embed in the session JSON. "
            "Defaults to the session directory path with a trailing slash."
        ),
    )
    args = parser.parse_args(argv)

    session_dir = Path(args.session_dir)
    session_json = build_session_from_oral_exam(
        session_dir,
        recording_uri=args.recording_uri,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(session_json, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

