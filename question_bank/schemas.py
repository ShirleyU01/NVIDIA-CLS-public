from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ParsedPage(BaseModel):
    page_index: int
    text: str
    char_count: int = 0

    def model_post_init(self, __context: Any) -> None:
        if not self.char_count:
            object.__setattr__(self, "char_count", len(self.text))


class ParsedDocument(BaseModel):
    course: str
    document_role: Literal["lecture", "exam", "solution", "review", "unknown"]
    source_path: str
    relative_path: str
    sha256: str
    title_guess: str
    pages: List[ParsedPage]
    ingested_at: str = Field(default_factory=utc_now_iso)


class ChunkRecord(BaseModel):
    chunk_id: str
    course: str
    source_type: str
    document_name: str
    source_path: str
    parsed_slug: str
    page_span: List[int]
    question_id: Optional[str] = None
    topic_hint: Optional[str] = None
    text: str


class EmbeddingManifest(BaseModel):
    embedding_model: str
    dim: int
    course: str
    chunk_file: str
    chunk_file_sha256: str
    num_vectors: int
    created_at: str = Field(default_factory=utc_now_iso)


class TopicContextChunk(BaseModel):
    chunk_id: str
    text: str
    source_type: str
    document_name: str
    score: float


class TopicContextBundle(BaseModel):
    course: str
    topic_id: str
    topic_name: str
    queries_used: List[str]
    chunks: List[TopicContextChunk]
    built_at: str = Field(default_factory=utc_now_iso)


class RubricCanonical(BaseModel):
    full_credit: List[str] = Field(default_factory=list)
    partial_credit: List[str] = Field(default_factory=list)
    common_mistakes: List[str] = Field(default_factory=list)


class FollowUpCanonical(BaseModel):
    condition: str
    question: str


class CanonicalQuestion(BaseModel):
    question_id: str
    course: str
    topic_id: str
    question_type: str
    difficulty: str
    question: str
    expected_answer: str
    source_chunk_ids: List[str]
    hints: List[str] = Field(default_factory=list)
    rubric: RubricCanonical = Field(default_factory=RubricCanonical)
    follow_ups: List[FollowUpCanonical] = Field(default_factory=list)

    @field_validator("hints", mode="before")
    @classmethod
    def normalize_hints(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]
