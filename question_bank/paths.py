from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Repository root (parent of `question_bank/`)."""
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """
    Root for all pipeline checkpoints (parsed, chunks, embeddings, …).

    Override for isolated test runs, e.g.:

        export QUESTION_BANK_DATA_ROOT="$PWD/question_bank_test_data"
        python -m question_bank.pipeline --course CS109 --through export
    """
    override = (os.environ.get("QUESTION_BANK_DATA_ROOT") or "").strip()
    if override:
        p = Path(override).expanduser()
        if not p.is_absolute():
            p = (repo_root() / p).resolve()
        else:
            p = p.resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    return repo_root() / "question_bank_data"


def raw_course_dir(course: str) -> Path:
    return data_dir() / "raw" / course


def parsed_dir() -> Path:
    d = data_dir() / "parsed"
    d.mkdir(parents=True, exist_ok=True)
    return d


def chunks_dir() -> Path:
    d = data_dir() / "chunks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def chunks_jsonl_path(course: str) -> Path:
    return chunks_dir() / f"{course}.jsonl"


def embeddings_dir(course: str) -> Path:
    d = data_dir() / "embeddings" / course
    d.mkdir(parents=True, exist_ok=True)
    return d


def topic_contexts_dir(course: str) -> Path:
    d = data_dir() / "topic_contexts" / course
    d.mkdir(parents=True, exist_ok=True)
    return d


def generated_dir(course: str) -> Path:
    d = data_dir() / "generated_questions" / course
    d.mkdir(parents=True, exist_ok=True)
    return d


def final_bank_dir(course: str) -> Path:
    d = data_dir() / "final_question_bank" / course
    d.mkdir(parents=True, exist_ok=True)
    return d


def pipeline_state_dir() -> Path:
    d = data_dir() / ".pipeline_state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def configs_dir() -> Path:
    return Path(__file__).resolve().parent / "configs"


def topics_config_path(course: str) -> Path:
    """Convention: configs/<course_lower>_topics.yaml"""
    return configs_dir() / f"{course.lower()}_topics.yaml"
