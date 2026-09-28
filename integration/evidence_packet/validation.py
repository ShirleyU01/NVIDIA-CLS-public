"""
Deterministic validation of LLM evidence packet items.
"""

from __future__ import annotations

from typing import Any, Dict, List

from integration.evidence_packet.models import QABlock


def _all_screenshot_timestamps(blocks: List[QABlock]) -> set[float]:
    out: set[float] = set()
    for b in blocks:
        for s in b.screenshots:
            out.add(s.timestamp)
    return out


def validate_packet_item(item: Dict[str, Any], blocks: List[QABlock]) -> List[str]:
    """
    Validate one per-criterion packet item against session QA blocks.
    Returns a list of validation flag strings (empty if valid).
    """
    flags: List[str] = []
    all_answers = {b.block_id: b.student_answer for b in blocks}
    all_text = "\n".join(all_answers.values())
    valid_timestamps = _all_screenshot_timestamps(blocks)

    for ev in item.get("evidence", []):
        if ev.get("type") == "transcript_quote":
            q = ev.get("quote", "")
            if not q or q not in all_text:
                flags.append("invalid_quote_not_found_in_answers")
        t0, t1 = ev.get("t0"), ev.get("t1")
        if (t0 is None) != (t1 is None):
            flags.append("invalid_partial_timestamp")
        if t0 is not None and t0 not in valid_timestamps:
            flags.append("invalid_timestamp_not_in_screenshots")
        if t1 is not None and t1 not in valid_timestamps:
            flags.append("invalid_timestamp_not_in_screenshots")

    # video_event evidence
    for ev in item.get("evidence", []):
        if ev.get("type") == "video_event":
            t0, t1 = ev.get("t0"), ev.get("t1")
            if (t0 is None) != (t1 is None):
                flags.append("invalid_partial_timestamp")
            if t0 is not None and t0 not in valid_timestamps:
                flags.append("invalid_timestamp_not_in_screenshots")
            if t1 is not None and t1 not in valid_timestamps:
                flags.append("invalid_timestamp_not_in_screenshots")

    if "llm_confidence" in item:
        c = item["llm_confidence"]
        if not isinstance(c, (int, float)) or c < 0 or c > 1:
            flags.append("invalid_llm_confidence_range")

    if item.get("score", 0) > 0 and len(item.get("evidence", [])) == 0:
        flags.append("score_without_evidence")

    return flags
