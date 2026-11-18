"""A small in-process vector store (exact cosine search with numpy).

Why not Chroma/FAISS? For one repository (a few thousand chunks at most) an exact dot-product
over a numpy matrix takes milliseconds, has zero extra dependencies and is trivially correct.
The interface (`add` / `search`) is deliberately tiny so it can be swapped for ChromaDB, FAISS
or pgvector later without touching the rest of the app.
"""
from __future__ import annotations

from typing import Generic, TypeVar

import numpy as np

T = TypeVar("T")


class VectorStore(Generic[T]):
    def __init__(self) -> None:
        self._matrix: np.ndarray | None = None
        self._items: list[T] = []

    def __len__(self) -> int:
        return len(self._items)

    def add(self, vectors: np.ndarray, items: list[T]) -> None:
        if len(items) != vectors.shape[0]:
            raise ValueError("vectors and items must have the same length")
        if self._matrix is not None and vectors.shape[1] != self._matrix.shape[1]:
            raise ValueError("vector dimension mismatch")
        self._matrix = vectors if self._matrix is None else np.vstack([self._matrix, vectors])
        self._items.extend(items)

    def search(self, query: np.ndarray, k: int) -> list[tuple[T, float]]:
        """Return the k most similar (item, cosine score) pairs, best first."""
        if self._matrix is None or not self._items:
            return []
        q = np.asarray(query, dtype=np.float32).reshape(-1)
        scores = self._matrix @ q
        k = min(k, len(self._items))
        idx = np.argpartition(-scores, k - 1)[:k]
        idx = idx[np.argsort(-scores[idx])]
        return [(self._items[i], float(scores[i])) for i in idx]

    def scores(self, query: np.ndarray) -> np.ndarray:
        """Cosine score of the query against EVERY stored item (aligned with insertion order)."""
        if self._matrix is None:
            return np.zeros(0, dtype=np.float32)
        return self._matrix @ np.asarray(query, dtype=np.float32).reshape(-1)

    @property
    def items(self) -> list[T]:
        return self._items
