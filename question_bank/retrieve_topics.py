from __future__ import annotations

import argparse
import json
from pathlib import Path

from question_bank.faiss_index import read_index, search
from question_bank.llm import embed_texts
from question_bank.paths import embeddings_dir, repo_root, topic_contexts_dir, topics_config_path
from question_bank.schemas import ChunkRecord, TopicContextBundle, TopicContextChunk
from question_bank.topics_config import build_queries_for_topic, load_topics_config


def load_chunks_meta(course: str) -> list[ChunkRecord]:
    path = embeddings_dir(course) / "chunks_meta.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}; run embed first")
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ChunkRecord.model_validate(x) for x in data]


def main() -> None:
    p = argparse.ArgumentParser(description="Job D: retrieve chunks per topic")
    p.add_argument("--course", required=True)
    p.add_argument(
        "--topics-yaml",
        type=Path,
        default=None,
        help="Defaults to question_bank/configs/<course>_topics.yaml",
    )
    args = p.parse_args()

    cfg_path = args.topics_yaml or topics_config_path(args.course)
    if not cfg_path.exists():
        print(f"Missing topics config: {cfg_path}")
        raise SystemExit(1)

    cfg = load_topics_config(cfg_path)
    if cfg.course.upper() != args.course.upper():
        print(f"Warning: YAML course={cfg.course} differs from --course={args.course}")

    index_path = embeddings_dir(args.course) / "index.faiss"
    if not index_path.exists():
        print(f"Missing FAISS index: {index_path}")
        raise SystemExit(1)

    index = read_index(index_path)
    chunks = load_chunks_meta(args.course)
    model = cfg.embedding_model

    out_dir = topic_contexts_dir(args.course)
    top_k = cfg.retrieve.top_k_per_query
    cap = cfg.retrieve.max_chunks_per_topic

    for topic in cfg.topics:
        queries = build_queries_for_topic(cfg, topic)[:28]
        if not queries:
            continue
        q_vecs = embed_texts(queries, model=model)
        dist, idx = search(index, q_vecs, top_k)

        scored: dict[str, float] = {}
        for row in range(idx.shape[0]):
            for col in range(idx.shape[1]):
                i = int(idx[row, col])
                if i < 0 or i >= len(chunks):
                    continue
                cid = chunks[i].chunk_id
                sc = float(dist[row, col])
                scored[cid] = max(scored.get(cid, -1e9), sc)

        ranked = sorted(scored.items(), key=lambda x: -x[1])[:cap]
        bundle_chunks: list[TopicContextChunk] = []
        for cid, sc in ranked:
            rec = next(c for c in chunks if c.chunk_id == cid)
            bundle_chunks.append(
                TopicContextChunk(
                    chunk_id=rec.chunk_id,
                    text=rec.text,
                    source_type=rec.source_type,
                    document_name=rec.document_name,
                    score=sc,
                )
            )

        bundle = TopicContextBundle(
            course=args.course,
            topic_id=topic.id,
            topic_name=topic.name,
            queries_used=queries,
            chunks=bundle_chunks,
        )
        out_path = out_dir / f"{topic.id}.json"
        out_path.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
        print(f"wrote {out_path.relative_to(repo_root())} ({len(bundle_chunks)} chunks)")

    print("retrieve_topics done")


if __name__ == "__main__":
    main()
