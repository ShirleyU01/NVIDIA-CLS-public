"""
Append-only metrics log for student/day runs (Jetson-local).

This complements ``session_log`` which stores per-session logs under
``sessions/<session_id>/paper``. Metrics logging stores the same event stream
under a student-centric directory so we can later build dashboards:

metrics/students/<student_id>/day_runs/<day_run_id>/sessions/<session_id>/
  - events.jsonl
  - summary.json   (rollup: captures, AMA, paper vs oral counts, STT/grade latencies)
  - session_snapshot.json (question specs, captures_by_question, oral_by_question, transcripts)

Oral-related event types (also mirrored from session_log):
  - answer_mode_set, oral_upload_started, oral_transcript, oral_feedback, oral_retake
  - client_event oral_record_started / oral_record_stopped (with record_duration_ms)

Design contract mirrors ``session_log``:
- never raise (telemetry must not break grading)
- JSONL appends are serialized behind a lock
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_WRITE_LOCK = threading.Lock()


def _normalize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    out["ts"] = event.get("ts", time.time())
    for k, v in event.items():
        if k == "ts":
            continue
        out[k] = v
    return out


def log_event(path: Path, event: Dict[str, Any]) -> None:
    """
    Append one event line to ``path`` (a JSONL file).
    Never raises.
    """
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _normalize_event(dict(event))
        line = json.dumps(payload, ensure_ascii=False, default=str) + "\n"
        with _WRITE_LOCK:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
    except Exception as e:  # pragma: no cover
        logger.warning("metrics_log.log_event failed: %s", e)


def read_events(path: Path) -> List[Dict[str, Any]]:
    if not Path(path).is_file():
        return []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    out: List[Dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            out.append(parsed)
    return out


def write_summary(path: Path, *, summary: Dict[str, Any]) -> Optional[Path]:
    """
    Best-effort write of a rollup JSON next to the JSONL file.
    """
    try:
        path = Path(path)
        out_path = path.with_name("summary.json")
        out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return out_path
    except Exception:  # pragma: no cover
        return None

