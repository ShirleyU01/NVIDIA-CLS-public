from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import numpy as np

try:
    import faiss  # type: ignore
except ImportError as e:
    faiss = None  # type: ignore


def require_faiss() -> None:
    if faiss is None:
        raise ImportError("faiss-cpu is required. pip install faiss-cpu")


def build_flat_ip_index(vectors: np.ndarray):
    """vectors: (n, d) float32, L2-normalized rows."""
    require_faiss()
    d = int(vectors.shape[1])
    index = faiss.IndexFlatIP(d)
    index.add(vectors.astype(np.float32))
    return index


def search(index, query_vectors: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
    """Returns distances, indices (both numpy arrays)."""
    require_faiss()
    q = query_vectors.astype(np.float32)
    return index.search(q, k)


def write_index(index, path: Path) -> None:
    require_faiss()
    path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(path))


def read_index(path: Path):
    require_faiss()
    return faiss.read_index(str(path))
