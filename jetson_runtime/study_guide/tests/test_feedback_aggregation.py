"""
Tests for :func:`aggregate_study_session`.

Uses ``tmp_path`` to lay down fake captures and asserts:

- Empty / missing directories return ``[]`` (no crash).
- Captures come back oldest-first using mtime.
- Per-capture sidecar JSON/MD files are picked up automatically when present.
- The shared ``paper_feedback.json`` / ``.md`` (today's writer behavior) gets
  attached to the *last* capture when no per-capture file exists.
- Malformed JSON files are tolerated (record gets an empty dict, no crash).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve()
_jetson_runtime = _HERE.parents[2]
if str(_jetson_runtime) not in sys.path:
    sys.path.insert(0, str(_jetson_runtime))

from study_guide.feedback_aggregation import (  # noqa: E402
    CaptureRecord,
    aggregate_study_session,
)


def _touch_image(path: Path, *, mtime: float) -> None:
    """Create an empty ``.jpg`` and stamp its mtime so ordering is deterministic."""
    path.write_bytes(b"\xff\xd8\xff\xd9")  # minimal JPEG-like bytes
    os.utime(path, (mtime, mtime))


def test_empty_directory_returns_empty_list(tmp_path: Path):
    assert aggregate_study_session(tmp_path) == []


def test_missing_directory_returns_empty_list(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    assert aggregate_study_session(missing) == []


def test_captures_ordered_by_mtime(tmp_path: Path):
    base = time.time()
    _touch_image(tmp_path / "paper_2.jpg", mtime=base + 200)
    _touch_image(tmp_path / "paper_1.jpg", mtime=base + 100)
    _touch_image(tmp_path / "paper_3.jpg", mtime=base + 300)

    records = aggregate_study_session(tmp_path)
    assert [r.image_filename for r in records] == ["paper_1.jpg", "paper_2.jpg", "paper_3.jpg"]
    assert [r.index for r in records] == [1, 2, 3]


def test_per_capture_sidecar_files_attached(tmp_path: Path):
    base = time.time()
    _touch_image(tmp_path / "paper_100.jpg", mtime=base + 1)
    _touch_image(tmp_path / "paper_200.jpg", mtime=base + 2)

    (tmp_path / "paper_100.json").write_text(
        json.dumps({"summary": "first capture"}), encoding="utf-8"
    )
    (tmp_path / "paper_100.md").write_text("first md", encoding="utf-8")
    (tmp_path / "paper_200.json").write_text(
        json.dumps({"summary": "second capture"}), encoding="utf-8"
    )
    (tmp_path / "paper_200.md").write_text("second md", encoding="utf-8")

    records = aggregate_study_session(tmp_path)
    assert records[0].feedback_json == {"summary": "first capture"}
    assert records[0].feedback_md == "first md"
    assert records[1].feedback_json == {"summary": "second capture"}
    assert records[1].feedback_md == "second md"


def test_shared_feedback_attached_to_last_capture(tmp_path: Path):
    """
    Today the writer overwrites a single shared paper_feedback.json/.md per
    session. Make sure the aggregator attaches that to the LAST capture only.
    """
    base = time.time()
    _touch_image(tmp_path / "paper_a.jpg", mtime=base + 1)
    _touch_image(tmp_path / "paper_b.jpg", mtime=base + 2)
    (tmp_path / "paper_feedback.json").write_text(
        json.dumps({"summary": "latest grade"}), encoding="utf-8"
    )
    (tmp_path / "paper_feedback.md").write_text("latest md", encoding="utf-8")

    records = aggregate_study_session(tmp_path)
    assert records[0].feedback_json == {}
    assert records[0].feedback_md == ""
    assert records[1].feedback_json == {"summary": "latest grade"}
    assert records[1].feedback_md == "latest md"


def test_per_capture_takes_precedence_over_shared(tmp_path: Path):
    base = time.time()
    _touch_image(tmp_path / "paper_z.jpg", mtime=base + 1)
    (tmp_path / "paper_z.json").write_text(
        json.dumps({"summary": "per-capture wins"}), encoding="utf-8"
    )
    (tmp_path / "paper_feedback.json").write_text(
        json.dumps({"summary": "shared loses"}), encoding="utf-8"
    )

    records = aggregate_study_session(tmp_path)
    assert records[0].feedback_json == {"summary": "per-capture wins"}


def test_malformed_json_is_tolerated(tmp_path: Path):
    base = time.time()
    _touch_image(tmp_path / "paper_x.jpg", mtime=base + 1)
    (tmp_path / "paper_x.json").write_text("{ not valid json", encoding="utf-8")
    (tmp_path / "paper_x.md").write_text("still readable", encoding="utf-8")

    records = aggregate_study_session(tmp_path)
    assert records[0].feedback_json == {}
    assert records[0].feedback_md == "still readable"


def test_capture_record_default_dict_is_independent():
    """
    Regression: dataclass mutable default must not be shared across instances.
    """
    a = CaptureRecord(index=1, image_filename="a.jpg")
    b = CaptureRecord(index=2, image_filename="b.jpg")
    a.feedback_json["k"] = "v"
    assert "k" not in b.feedback_json
