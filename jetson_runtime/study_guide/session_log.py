"""
Append-only interaction log for a study run.

During a study session the Jetson already persists JPEGs, per-capture grader
feedback, and the end-of-session summary. This module is a *parallel*,
additive log that records the full student <-> LLM interaction stream so we
can reconstruct exactly what the student saw and said:

- ``run_started``      - run + question specs, emitted once at create time.
- ``question_shown``   - every time ``runtime.current_index`` advances.
- ``capture``          - every JPEG written by capture / capture-upload.
- ``capture_feedback`` - per-capture immediate-feedback LLM reply.
- ``ama_turn``         - each student or tutor turn in the side chatbot.
- ``oral_transcript``  - STT result after a spoken answer upload.
- ``answer_mode_set``  - student chose paper vs oral for a question.
- ``helper_action``    - ``understand`` / ``lost`` / ``question`` helper-bot
  replies.

On-disk layout (under ``settings.SESSIONS_DIR / <session_id> / paper/``):

- ``interactions.jsonl`` - append-only JSON-lines, one event per line.
- ``interactions.json``  - pretty rollup written at ``/end`` with
  ``{session_id, events, summary}``.

Design contract:

* Callers MUST pass a ``session_dir`` that is the ``paper/`` folder for that
  session (same directory we already use for ``study_feedback.json``).
* ``log_event`` never raises - any I/O failure is swallowed and logged so the
  grading / HTTP pipeline is never blocked by a telemetry hiccup.
* Non-JSON-serializable values (``Path``, ``datetime``, custom dataclasses)
  are coerced via ``json.dumps(..., default=str)`` so callers can hand in
  ordinary Python objects.
* Appends are serialized behind a process-wide ``threading.Lock`` so
  concurrent background threads (grading workers + HTTP handlers) never
  interleave a JSON line.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


_JSONL_FILENAME = "interactions.jsonl"
_ROLLUP_FILENAME = "interactions.json"

# Serialize appends so concurrent background threads (capture grading +
# /action handlers) can never produce an interleaved JSON line.
_WRITE_LOCK = threading.Lock()


def _jsonl_path(session_dir: Path) -> Path:
    return Path(session_dir) / _JSONL_FILENAME


def _rollup_path(session_dir: Path) -> Path:
    return Path(session_dir) / _ROLLUP_FILENAME


def _normalize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a copy of ``event`` with a guaranteed ``ts`` float (Unix seconds)
    at the front. We do *not* overwrite an existing ``ts`` so callers can
    supply deterministic timestamps in tests.
    """
    out: Dict[str, Any] = {}
    if "ts" in event:
        out["ts"] = event["ts"]
    else:
        out["ts"] = time.time()
    for k, v in event.items():
        if k == "ts":
            continue
        out[k] = v
    return out


def log_event(session_dir: Path, event: Dict[str, Any]) -> None:
    """
    Append one event line to ``<session_dir>/interactions.jsonl``.

    Never raises. On any failure we log a warning and move on so the caller
    (grading / HTTP handler) is never impacted by telemetry I/O.
    """
    try:
        session_dir = Path(session_dir)
        session_dir.mkdir(parents=True, exist_ok=True)
        payload = _normalize_event(dict(event))
        line = json.dumps(payload, ensure_ascii=False, default=str) + "\n"
        target = _jsonl_path(session_dir)
        with _WRITE_LOCK:
            # Open / append / close per event keeps the file valid even if
            # the process is killed mid-run (no long-lived file handle).
            with open(target, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
    except Exception as e:  # pragma: no cover - defensive only
        logger.warning("session_log.log_event failed: %s", e)


def read_events(session_dir: Path) -> List[Dict[str, Any]]:
    """
    Read every JSON line from ``<session_dir>/interactions.jsonl``.

    Tolerant:
    - missing file or directory -> ``[]``
    - any line that fails to parse is skipped (logged at DEBUG) and the
      remaining valid lines are still returned.
    """
    path = _jsonl_path(session_dir)
    if not path.exists() or not path.is_file():
        return []

    events: List[Dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:  # pragma: no cover - defensive only
        logger.warning("session_log.read_events could not read %s: %s", path, e)
        return []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("session_log.read_events skipping bad line: %r", line[:200])
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


def finalize(session_dir: Path, *, extra: Optional[Dict[str, Any]] = None) -> Path:
    """
    Read the JSONL timeline and write ``<session_dir>/interactions.json``
    with shape::

        {
          "session_id": "<folder name of the parent dir>",
          "events": [... JSONL events in the order they were written ...],
          "summary": extra or {}
        }

    Returns the path of the rollup file. Creates ``session_dir`` if needed.
    """
    session_dir = Path(session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)

    # ``paper/`` lives under ``sessions/<session_id>/paper/``; the session_id
    # is the parent folder's name. Fall back to the paper folder name if the
    # caller gave us a non-standard layout.
    parent = session_dir.parent
    session_id = parent.name if parent and parent.name else session_dir.name

    events = read_events(session_dir)
    payload: Dict[str, Any] = {
        "session_id": session_id,
        "events": events,
        "summary": dict(extra) if extra else {},
    }
    out_path = _rollup_path(session_dir)
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return out_path
