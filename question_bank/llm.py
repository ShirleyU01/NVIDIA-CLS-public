from __future__ import annotations

import os
from typing import List

import numpy as np


def embed_texts(
    texts: List[str],
    *,
    model: str | None = None,
    batch_size: int = 64,
) -> np.ndarray:
    """
    Return float32 array shape (n, d) with L2-normalized rows for inner-product ~ cosine similarity.
    """
    try:
        from openai import OpenAI
    except ImportError as e:
        raise ImportError("openai package required. pip install openai") from e

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    model = model or os.environ.get("QUESTION_BANK_EMBEDDING_MODEL", "text-embedding-3-small")
    client = OpenAI(api_key=api_key)
    all_vecs: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(model=model, input=batch)
        # API returns in request order
        by_idx = sorted(resp.data, key=lambda x: x.index)
        for row in by_idx:
            all_vecs.append(row.embedding)

    arr = np.array(all_vecs, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    arr = arr / norms
    return arr
