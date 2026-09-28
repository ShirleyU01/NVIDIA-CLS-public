from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from question_bank.faiss_index import build_flat_ip_index, write_index
from question_bank.llm import embed_texts
from question_bank.paths import chunks_jsonl_path, embeddings_dir, repo_root
from question_bank.schemas import ChunkRecord, EmbeddingManifest


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_chunks(path: Path) -> list[ChunkRecord]:
    rows: list[ChunkRecord] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(ChunkRecord.model_validate_json(line))
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description="Job C: chunks JSONL → FAISS index")
    p.add_argument("--course", required=True)
    p.add_argument("--embedding-model", default=None, help="Override env / topics yaml")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    chunk_path = chunks_jsonl_path(args.course)
    if not chunk_path.exists():
        print(f"Missing chunks file: {chunk_path}")
        raise SystemExit(1)

    digest = sha256_file(chunk_path)
    emb_dir = embeddings_dir(args.course)
    index_path = emb_dir / "index.faiss"
    meta_path = emb_dir / "chunks_meta.json"
    manifest_path = emb_dir / "manifest.json"

    if (
        not args.force
        and manifest_path.exists()
        and index_path.exists()
        and meta_path.exists()
    ):
        try:
            prev = json.loads(manifest_path.read_text(encoding="utf-8"))
            if prev.get("chunk_file_sha256") == digest:
                print("embed: unchanged chunk file, skipping (use --force)")
                return
        except (json.JSONDecodeError, OSError):
            pass

    chunks = read_chunks(chunk_path)
    if not chunks:
        print("No chunks in file")
        raise SystemExit(1)

    texts = [c.text for c in chunks]
    model = args.embedding_model or __import__("os").environ.get(
        "QUESTION_BANK_EMBEDDING_MODEL", "text-embedding-3-small"
    )
    vecs = embed_texts(texts, model=model)
    index = build_flat_ip_index(vecs)
    write_index(index, index_path)

    meta = [c.model_dump() for c in chunks]
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    man = EmbeddingManifest(
        embedding_model=model,
        dim=int(vecs.shape[1]),
        course=args.course,
        chunk_file=str(chunk_path.relative_to(repo_root())),
        chunk_file_sha256=digest,
        num_vectors=len(chunks),
    )
    manifest_path.write_text(man.model_dump_json(indent=2), encoding="utf-8")
    print(f"wrote index → {index_path.relative_to(repo_root())}")
    print(f"vectors={len(chunks)} dim={vecs.shape[1]} model={model}")


if __name__ == "__main__":
    main()
