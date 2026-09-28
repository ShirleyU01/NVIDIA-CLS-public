"""
One-shot CLI: oral exam session folder -> normalized session JSON -> evidence packet.

This is the glue between:
- jetson_runtime oral exam outputs under jetson_runtime/sessions/<session_id>/
- integration.evidence_packet pipeline (rubric + session JSON -> evidence_packet.json)
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from integration.build_session_from_oral_exam import build_session_from_oral_exam
from integration.evidence_packet import run_evidence_packet


def _select_default_recording_uri(session_dir: Path, mode: str) -> str:
    if mode == "mp4":
        mp4 = session_dir / "recording.mp4"
        if mp4.is_file():
            return mp4.as_posix()
    # Default: directory-style URI mirroring fixtures
    return session_dir.as_posix() + "/"


def _extract_criterion_id(user_prompt: str) -> str:
    m = re.search(r"^\- criterion_id:\s*(\S+)\s*$", user_prompt, flags=re.MULTILINE)
    return m.group(1) if m else ""


def _extract_blocks_json(user_prompt: str) -> List[Dict[str, Any]]:
    """
    Parse the JSON array embedded in the evidence-packet user prompt.
    We rely on the known markers from integration.evidence_packet.prompts.build_user_prompt.
    """
    marker_a = "Session QA blocks (ONLY sources of quotes and timestamps):\n"
    marker_b = "\n\nTask:\n"
    start = user_prompt.find(marker_a)
    if start == -1:
        return []
    start = start + len(marker_a)
    end = user_prompt.find(marker_b, start)
    if end == -1:
        return []
    raw = user_prompt[start:end].strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _mock_llm(system_prompt: str, user_prompt: str) -> str:
    """
    Deterministic mock LLM for smoke testing without API keys.

    Returns a per-criterion JSON payload that should pass validation:
    - quote is a substring of some student_answer (or score=0 if no text)
    - timestamps are either null or from provided screenshots
    """
    cid = _extract_criterion_id(user_prompt) or "C1"
    blocks = _extract_blocks_json(user_prompt)

    chosen_answer = ""
    chosen_timestamp: Optional[float] = None
    if blocks:
        for b in blocks:
            ans = str(b.get("student_answer", "")).strip()
            if ans:
                chosen_answer = ans
                shots = b.get("screenshots", []) or []
                if shots:
                    chosen_timestamp = float(shots[0].get("timestamp"))
                break

    evidence: List[Dict[str, Any]] = []
    flags: List[str] = []

    if not chosen_answer:
        score = 0
        score_anchor = "0"
        llm_confidence = 0.3
        missing_evidence = ["No student answer text available in session blocks."]
        suggested_followup = "Can you restate your answer with more detail?"
    else:
        # Pick a short snippet that is guaranteed to be a substring.
        snippet = chosen_answer[:80].strip()
        if not snippet:
            score = 0
            score_anchor = "0"
            llm_confidence = 0.3
            missing_evidence = ["Student answer text is empty."]
            suggested_followup = "Can you provide your reasoning step by step?"
        else:
            score = 1
            score_anchor = "1"
            llm_confidence = 0.6
            missing_evidence = []
            suggested_followup = "Can you provide one concrete example?"
            if chosen_timestamp is None:
                t0 = None
                t1 = None
                flags.append("missing_timestamp_for_quote")
            else:
                t0 = chosen_timestamp
                t1 = chosen_timestamp
            evidence.append(
                {
                    "type": "transcript_quote",
                    "quote": snippet,
                    "t0": t0,
                    "t1": t1,
                    "why_it_supports": "Smoke-test evidence extracted from the session text.",
                }
            )

    payload = {
        "criterion_id": cid,
        "score": score,
        "score_rationale_anchor": score_anchor,
        "llm_confidence": llm_confidence,
        "evidence": evidence,
        "missing_evidence": missing_evidence,
        "suggested_followup_question": suggested_followup,
        "flags": flags,
    }
    return json.dumps(payload)


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Generate an evidence packet from a jetson_runtime oral exam session folder."
    )
    parser.add_argument(
        "--session-dir",
        required=True,
        help="Path to jetson_runtime/sessions/<session_id>/ (must contain transcript.json + final_transcript.json)",
    )
    parser.add_argument("--rubric", required=True, help="Path to rubric JSON")
    parser.add_argument("--out", required=True, help="Output path for evidence_packet.json")
    parser.add_argument(
        "--session-out",
        default=None,
        help=(
            "Optional path to write the normalized session JSON. "
            "If omitted, it will be written next to --out as '<out>.session.json'."
        ),
    )
    parser.add_argument(
        "--recording-uri",
        default=None,
        help="Override recording_uri embedded in the normalized session JSON.",
    )
    parser.add_argument(
        "--recording-uri-mode",
        choices=["dir", "mp4"],
        default="dir",
        help="If --recording-uri is not provided, choose recording_uri as session dir (dir) or recording.mp4 path (mp4).",
    )
    parser.add_argument(
        "--llm",
        choices=["auto", "mock"],
        default="auto",
        help="LLM backend: auto uses OpenAI if OPENAI_API_KEY is set; mock is deterministic and needs no API key.",
    )
    args = parser.parse_args(argv)

    session_dir = Path(args.session_dir).resolve()
    if args.recording_uri is not None:
        recording_uri = args.recording_uri
    else:
        recording_uri = _select_default_recording_uri(session_dir, args.recording_uri_mode)

    normalized = build_session_from_oral_exam(session_dir, recording_uri=recording_uri)

    out_path = Path(args.out)
    session_out = Path(args.session_out) if args.session_out else Path(str(out_path) + ".session.json")
    session_out.parent.mkdir(parents=True, exist_ok=True)
    with session_out.open("w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    llm_fn = None
    if args.llm == "mock":
        llm_fn = _mock_llm
    else:
        if os.environ.get("OPENAI_API_KEY"):
            from integration.evidence_packet import llm_openai

            llm_fn = llm_openai.llm_complete

    if llm_fn is None:
        raise RuntimeError(
            "No LLM configured. Set OPENAI_API_KEY for --llm auto, or run with --llm mock."
        )

    run_evidence_packet(args.rubric, str(session_out), args.out, llm_complete_fn=llm_fn)


if __name__ == "__main__":
    main()

