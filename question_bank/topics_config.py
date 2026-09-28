from __future__ import annotations

from pathlib import Path
from typing import Any, List

import yaml
from pydantic import BaseModel, Field


class RetrieveSettings(BaseModel):
    top_k_per_query: int = 8
    max_chunks_per_topic: int = 40


class TopicEntry(BaseModel):
    id: str
    name: str
    aliases: List[str] = Field(default_factory=list)
    query_templates: List[str] = Field(default_factory=list)


class TopicsConfigFile(BaseModel):
    course: str
    embedding_model: str = "text-embedding-3-small"
    generation_model: str = "gpt-4o"
    retrieve: RetrieveSettings = Field(default_factory=RetrieveSettings)
    default_query_templates: List[str] = Field(
        default_factory=lambda: [
            "{name} definition",
            "{name} intuition",
            "{name} worked example",
            "{name} common mistakes",
            "{name} exam problem",
        ]
    )
    topics: List[TopicEntry] = Field(default_factory=list)


def load_topics_config(path: Path) -> TopicsConfigFile:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid YAML root in {path}")
    return TopicsConfigFile.model_validate(raw)


def build_queries_for_topic(cfg: TopicsConfigFile, topic: TopicEntry) -> List[str]:
    templates = topic.query_templates or cfg.default_query_templates
    out: List[str] = []
    seen: set[str] = set()
    name = topic.name

    def add(q: str) -> None:
        q = " ".join(q.split())
        if q and q not in seen:
            seen.add(q)
            out.append(q)

    for tpl in templates:
        if "{alias}" in tpl:
            for al in topic.aliases:
                add(tpl.format(name=name, alias=al))
        else:
            add(tpl.format(name=name, alias=""))
    for al in topic.aliases:
        add(f"{al} overview")
        add(f"{al} practice")
    return out
