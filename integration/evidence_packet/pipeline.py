"""
Evidence packet pipeline: load rubric/session, call LLM per criterion, validate, assemble.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from integration.evidence_packet.llm import llm_complete
from integration.evidence_packet.models import QABlock, Screenshot
from integration.evidence_packet.prompts import build_system_prompt, build_user_prompt
from integration.evidence_packet.validation import validate_packet_item


def load_rubric(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_session(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_blocks(session: Dict[str, Any]) -> Tuple[str, str, List[QABlock]]:
    recording_uri = session.get("recording_uri", "")
    session_id = session.get("session_id", "unknown_session")
    blocks: List[QABlock] = []
    for b in session.get("qa_blocks", []):
        shots = [
            Screenshot(
                timestamp=float(s["timestamp"]),
                image_id=str(s.get("image_id", "")),
                region=s.get("region"),
            )
            for s in b.get("screenshots", [])
        ]
        main_response = str(b.get("main_response", "")).strip()
        follow_up_responses = b.get("follow_up_responses")
        if not isinstance(follow_up_responses, list):
            follow_up_responses = []
        follow_up_responses = [str(x).strip() for x in follow_up_responses if str(x).strip()]
        blocks.append(
            QABlock(
                block_id=str(b["block_id"]),
                question=str(b["question"]),
                student_answer=str(b["student_answer"]),
                screenshots=shots,
                main_response=main_response,
                follow_up_responses=follow_up_responses,
            )
        )
    return session_id, recording_uri, blocks


def _is_probable_filesystem_path(s: str) -> bool:
    if not s:
        return False
    # Avoid treating URIs like s3://, http://, jetson:// as local paths.
    if "://" in s:
        return False
    return True


def _candidate_base_dirs(session_path: str, recording_uri: str) -> List[Path]:
    bases: List[Path] = []
    try:
        bases.append(Path(session_path).resolve().parent)
    except Exception:
        pass

    if _is_probable_filesystem_path(recording_uri):
        try:
            p = Path(recording_uri).expanduser()
            if p.exists():
                bases.append(p.resolve() if p.is_dir() else p.resolve().parent)
        except Exception:
            pass

    # De-dup while preserving order
    seen: set[str] = set()
    out: List[Path] = []
    for b in bases:
        k = b.as_posix()
        if k not in seen:
            seen.add(k)
            out.append(b)
    return out


def _resolve_screenshot_file(image_id: str, base_dirs: List[Path]) -> Optional[Path]:
    if not image_id:
        return None
    p = Path(image_id).expanduser()
    if p.is_file():
        return p
    for base in base_dirs:
        cand = (base / image_id).resolve()
        if cand.is_file():
            return cand
    return None


def _build_vision_images(
    *,
    blocks: List[QABlock],
    session_path: str,
    recording_uri: str,
) -> List[Dict[str, Any]]:
    """
    Best-effort: attach a small number of screenshot images (data URLs) so a
    vision-capable model can analyze them.
    """
    # Vision is enabled by default. Set EVIDENCE_PACKET_VISION=0/false/no to disable.
    vision_flag = os.environ.get("EVIDENCE_PACKET_VISION", "1").strip().lower()
    if vision_flag in {"0", "false", "no"}:
        return []

    try:
        max_images = int(os.environ.get("EVIDENCE_PACKET_MAX_VISION_IMAGES", "6"))
    except Exception:
        max_images = 6

    try:
        max_bytes = int(os.environ.get("EVIDENCE_PACKET_MAX_IMAGE_BYTES", "1500000"))
    except Exception:
        max_bytes = 1500000

    if max_images <= 0 or max_bytes <= 0:
        return []

    base_dirs = _candidate_base_dirs(session_path, recording_uri)
    picked: List[Dict[str, Any]] = []
    seen_paths: set[str] = set()

    for b in blocks:
        for s in b.screenshots:
            if len(picked) >= max_images:
                return picked
            resolved = _resolve_screenshot_file(s.image_id, base_dirs)
            if not resolved:
                continue
            key = resolved.as_posix()
            if key in seen_paths:
                continue
            try:
                size = resolved.stat().st_size
            except Exception:
                continue
            if size > max_bytes:
                continue

            try:
                data = resolved.read_bytes()
            except Exception:
                continue

            mime = mimetypes.guess_type(resolved.name)[0] or "image/jpeg"
            b64 = base64.b64encode(data).decode("ascii")
            data_url = f"data:{mime};base64,{b64}"
            picked.append(
                {
                    "image_id": s.image_id,
                    "timestamp": s.timestamp,
                    "region": s.region,
                    "data_url": data_url,
                }
            )
            seen_paths.add(key)

    return picked


def _output_schema_for_criterion(criterion_id: str, criterion_max: int) -> Dict[str, Any]:
    return {
        "criterion_id": criterion_id,
        "score": 0,
        "score_rationale_anchor": "0|1|...",
        "llm_confidence": 0.0,
        "evidence": [
            {
                "type": "transcript_quote",
                "quote": "",
                "t0": None,
                "t1": None,
                "why_it_supports": "",
            },
            {
                "type": "video_event",
                "t0": None,
                "t1": None,
                "tag": "screenshot",
                "region": "",
            },
        ],
        "missing_evidence": [],
        "suggested_followup_question": "",
        "flags": [],
    }


def extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    # Strip markdown code fence if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    return json.loads(text)


def assemble_final_packet(
    session_id: str,
    recording_uri: str,
    rubric: Dict[str, Any],
    criterion_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    total_weighted = 0.0
    max_weighted = 0.0
    confidences: List[float] = []
    flags: List[str] = []

    crit_map = {c["id"]: c for c in rubric["criteria"]}

    for item in criterion_items:
        cid = item.get("criterion_id", "")
        crit = crit_map.get(cid, {})
        c_max = int(crit.get("max", rubric.get("scale", {}).get("max", 2)))
        w = float(crit.get("weight", 1.0))
        score = int(item.get("score", 0))
        score = max(0, min(c_max, score))
        total_weighted += score * w
        max_weighted += c_max * w
        confidences.append(float(item.get("llm_confidence", 0.0)))
        flags.extend(item.get("flags", []))

    overall_conf = min(confidences) if confidences else 0.0
    return {
        "session_id": session_id,
        "rubric_id": rubric.get("rubric_id", ""),
        "recording_uri": recording_uri,
        "total_score": total_weighted,
        "max_score": max_weighted,
        "overall_confidence": overall_conf,
        "criteria": criterion_items,
        "flags": sorted(list(set(flags))),
    }


def run_evidence_packet(
    rubric_path: str,
    session_path: str,
    out_path: str,
    *,
    llm_complete_fn: Optional[Any] = None,
) -> Dict[str, Any]:
    rubric = load_rubric(rubric_path)
    session = load_session(session_path)
    session_id, recording_uri, blocks = normalize_blocks(session)
    complete = llm_complete_fn or llm_complete
    system_prompt = build_system_prompt()
    lecture_material = (session.get("lecture_material") or "").strip()
    vision_images = _build_vision_images(
        blocks=blocks,
        session_path=session_path,
        recording_uri=recording_uri,
    )
    items: List[Dict[str, Any]] = []

    for criterion in rubric["criteria"]:
        cid = criterion.get("id", "")
        c_max = int(criterion.get("max", rubric.get("scale", {}).get("max", 2)))
        output_schema = _output_schema_for_criterion(cid, c_max)
        user_prompt = build_user_prompt(
            rubric, criterion, recording_uri, blocks, output_schema,
            lecture_material=lecture_material,
        )
        try:
            raw = complete(system_prompt, user_prompt, images=vision_images)
        except TypeError:
            raw = complete(system_prompt, user_prompt)
        item = extract_json(raw)
        item["criterion_id"] = cid
        item_flags = validate_packet_item(item, blocks)
        item["flags"] = sorted(list(set(item.get("flags", []) + item_flags)))
        items.append(item)

    # If the session includes actual follow-up questions asked during the exam,
    # use them word-for-word instead of the LLM-generated suggested_followup_question.
    asked_followups = session.get("asked_followup_questions") or []
    for i, item in enumerate(items):
        if i < len(asked_followups):
            item["suggested_followup_question"] = asked_followups[i]

    final_packet = assemble_final_packet(session_id, recording_uri, rubric, items)
    if asked_followups:
        final_packet["asked_followup_questions"] = list(asked_followups)
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(final_packet, f, ensure_ascii=False, indent=2)
    return final_packet


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Generate evidence packet from rubric + session JSON"
    )
    parser.add_argument("--rubric", required=True, help="Path to rubric JSON")
    parser.add_argument("--session", required=True, help="Path to session JSON")
    parser.add_argument("--out", required=True, help="Output path for evidence_packet.json")
    args = parser.parse_args(argv)

    llm_fn = None
    try:
        import os
        if os.environ.get("OPENAI_API_KEY"):
            from integration.evidence_packet import llm_openai
            llm_fn = llm_openai.llm_complete
    except Exception:
        pass
    run_evidence_packet(args.rubric, args.session, args.out, llm_complete_fn=llm_fn)


if __name__ == "__main__":
    main()
