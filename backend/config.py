from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


class Settings:
    """Simple settings object backed by environment variables."""

    def __init__(self) -> None:
        # Database URL (SQLite by default for local dev).
        self.DATABASE_URL = os.environ.get(
            "DATABASE_URL", "sqlite:///./socrates_backend.db"
        )

        # Root directory where Jetson (or a mounted volume) stores session folders.
        # In local dev we default to the repo jetson_runtime/sessions directory.
        repo_root = Path(__file__).resolve().parents[1]
        self.JETSON_SESSIONS_ROOT = Path(
            os.environ.get(
                "JETSON_SESSIONS_ROOT",
                repo_root / "jetson_runtime" / "sessions",
            )
        )

        # Where to write temporary normalized session JSON + evidence packets, if
        # we choose to keep them on disk as well as in the DB.
        self.EVIDENCE_PACKET_STORAGE_ROOT = Path(
            os.environ.get(
                "EVIDENCE_PACKET_STORAGE_ROOT",
                repo_root / "evidence_packets",
            )
        )

        # Optional OpenAI API key for cloud LLMs.
        self.OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

