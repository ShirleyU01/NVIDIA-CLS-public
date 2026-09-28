"""Per-question answer mode (paper vs oral) and on-disk artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

AnswerMode = Literal["paper", "oral"]


def question_dir(paper_root: Path, q_index: int) -> Path:
    return paper_root / f"q{int(q_index)}"


def oral_transcript_path(paper_root: Path, q_index: int) -> Path:
    return question_dir(paper_root, q_index) / "oral_transcript.txt"


def oral_transcript_json_path(paper_root: Path, q_index: int) -> Path:
    return question_dir(paper_root, q_index) / "oral_transcript.json"


def oral_feedback_md_path(paper_root: Path, q_index: int) -> Path:
    return question_dir(paper_root, q_index) / "oral_feedback.md"


def paper_feedback_md_path(paper_root: Path, q_index: int) -> Path:
    return question_dir(paper_root, q_index) / "paper_feedback.md"


def answer_modes_path(paper_root: Path) -> Path:
    return paper_root / "answer_modes.json"


def load_answer_modes(paper_root: Path) -> dict[str, str]:
    path = answer_modes_path(paper_root)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items() if v in ("paper", "oral")}
    except Exception:
        pass
    return {}


def save_answer_mode(paper_root: Path, q_index: int, mode: AnswerMode) -> None:
    paper_root.mkdir(parents=True, exist_ok=True)
    modes = load_answer_modes(paper_root)
    modes[str(int(q_index))] = mode
    answer_modes_path(paper_root).write_text(json.dumps(modes, indent=2), encoding="utf-8")


def get_answer_mode(paper_root: Path, q_index: int, *, default: AnswerMode = "paper") -> AnswerMode:
    modes = load_answer_modes(paper_root)
    m = modes.get(str(int(q_index)), default)
    return "oral" if m == "oral" else "paper"


def load_oral_transcript(paper_root: Path, q_index: int) -> tuple[str, dict[str, Any]]:
    txt_path = oral_transcript_path(paper_root, q_index)
    if txt_path.is_file():
        text = txt_path.read_text(encoding="utf-8", errors="replace").strip()
    else:
        text = ""
    meta: dict[str, Any] = {}
    json_path = oral_transcript_json_path(paper_root, q_index)
    if json_path.is_file():
        try:
            meta = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    if not text and isinstance(meta.get("text"), str):
        text = meta["text"].strip()
    return text, meta


def save_oral_transcript(
    paper_root: Path,
    q_index: int,
    *,
    text: str,
    segments: list[dict[str, Any]] | None = None,
    audio_filename: str = "",
) -> None:
    q_dir = question_dir(paper_root, q_index)
    q_dir.mkdir(parents=True, exist_ok=True)
    oral_transcript_path(paper_root, q_index).write_text(text.strip() + "\n", encoding="utf-8")
    payload = {
        "text": text.strip(),
        "segments": segments or [],
        "audio_filename": audio_filename,
    }
    oral_transcript_json_path(paper_root, q_index).write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def clear_oral_artifacts(paper_root: Path, q_index: int) -> None:
    q_dir = question_dir(paper_root, q_index)
    for name in (
        "oral_transcript.txt",
        "oral_transcript.json",
        "oral_feedback.md",
        "oral_feedback.json",
        "oral_upload.webm",
        "oral_upload.wav",
        "oral_upload.mp4",
        "oral_upload.m4a",
    ):
        p = q_dir / name
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass


def collect_graded_feedback_history(paper_root: Path, num_questions: int) -> str:
    """Prior per-question feedback (paper or oral) for AMA context."""
    if not paper_root.is_dir():
        return "(No graded work on disk yet.)\n"
    chunks: list[str] = []
    for i in range(max(0, int(num_questions))):
        mode = get_answer_mode(paper_root, i)
        if mode == "oral":
            md_path = oral_feedback_md_path(paper_root, i)
            label = "spoken answer"
        else:
            md_path = paper_feedback_md_path(paper_root, i)
            label = "paper capture"
        if not md_path.is_file():
            continue
        try:
            body = md_path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if not body:
            continue
        if len(body) > 7000:
            body = body[:7000] + "\n… (truncated)"
        chunks.append(f"### After {label} — question {i + 1} (folder q{i})\n{body}")
    return "\n\n".join(chunks) if chunks else "(No per-question graded feedback files yet.)\n"


def collect_oral_transcripts_for_ama(paper_root: Path, num_questions: int, current_index: int) -> str:
    """Spoken transcripts per question for AMA (including current question)."""
    if not paper_root.is_dir():
        return "(No spoken transcripts yet.)\n"
    lines: list[str] = ["## Student spoken answers (speech-to-text)"]
    any_text = False
    for i in range(max(0, int(num_questions))):
        text, _ = load_oral_transcript(paper_root, i)
        if not text.strip():
            continue
        any_text = True
        mark = " **← current question**" if i == current_index else ""
        snippet = text.strip()
        if len(snippet) > 4000:
            snippet = snippet[:4000] + "\n… (truncated)"
        lines.append(f"### Question {i + 1}{mark}\n{snippet}")
    if not any_text:
        return "(No spoken transcripts recorded yet.)\n"
    return "\n\n".join(lines)
