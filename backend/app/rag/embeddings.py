"""Turning text into vectors.

Two backends:

1. HashingEmbedder (default, works offline, no model download)
   A *code-aware lexical* embedding: identifiers are split (`calculateTotal` / `calculate_total`
   -> calculate, total), words are hashed into a fixed-size vector, and weighted by TF-IDF.
   Honest note: this matches on shared *words*; it does not understand synonyms the way a neural
   model does. It is deterministic, fast, and surprisingly good for "find the function that
   mentions X" -- but for semantic matching use backend 2.

2. SentenceTransformerEmbedder (optional: `pip install sentence-transformers`)
   A neural embedding model (default all-MiniLM-L6-v2). Captures meaning, needs a one-time
   model download and more CPU/RAM.

Both return L2-normalised float32 matrices, so cosine similarity == dot product.
"""
from __future__ import annotations

import math
import re
import zlib
from collections import Counter
from typing import Protocol

import numpy as np

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")
_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
# Words that appear in nearly all code and carry no signal.
_STOP = {"self", "cls", "def", "return", "import", "from", "the", "a", "an", "of", "to", "in",
         "is", "and", "or", "if", "else", "for", "as", "it", "this", "that", "with", "not", "none"}


def split_identifier(token: str) -> list[str]:
    """'calculateTotal_v2' -> ['calculate', 'total', 'v', '2'] (lower-cased)."""
    parts: list[str] = []
    for piece in token.split("_"):
        parts.extend(m.group(0).lower() for m in _CAMEL_RE.finditer(piece))
    return parts


_SUFFIXES = ("ing", "ers", "er", "ed", "es", "s")


def stem(word: str) -> str:
    """Tiny suffix stripper so 'counter', 'counting', 'counts' all match 'count'.

    Deliberately crude (no external NLP library). Short words and numbers are left alone.
    """
    if len(word) <= 4 or word.isdigit():
        return word
    for suf in _SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            return word[: -len(suf)]
    return word


def tokenize(text: str) -> list[str]:
    """Code-aware tokens: stemmed sub-words of identifiers, plus the whole identifier when it has several."""
    out: list[str] = []
    for m in _TOKEN_RE.finditer(text):
        tok = m.group(0)
        subs = split_identifier(tok)
        if len(subs) > 1:
            out.append(tok.lower())  # keep exact identifier so exact matches rank higher
        out.extend(stem(s) for s in subs if s not in _STOP)
    return [t for t in out if t not in _STOP and len(t) > 1]


class Embedder(Protocol):
    name: str

    def fit(self, texts: list[str]) -> None: ...
    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashingEmbedder:
    name = "hashing-tfidf"

    def __init__(self, dim: int = 4096):
        self.dim = dim
        self.idf = np.ones(dim, dtype=np.float32)

    def _bucket(self, token: str) -> int:
        return zlib.crc32(token.encode("utf-8")) % self.dim  # stable across runs (unlike hash())

    def fit(self, texts: list[str]) -> None:
        """Learn how rare each hashed word is across the repository (inverse document frequency)."""
        df = np.zeros(self.dim, dtype=np.float32)
        for t in texts:
            for b in {self._bucket(tok) for tok in tokenize(t)}:
                df[b] += 1
        n = max(len(texts), 1)
        self.idf = (np.log((1 + n) / (1 + df)) + 1.0).astype(np.float32)

    def embed(self, texts: list[str]) -> np.ndarray:
        mat = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            counts = Counter(self._bucket(tok) for tok in tokenize(t))
            for b, c in counts.items():
                mat[i, b] = (1.0 + math.log(c)) * self.idf[b]
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return mat / norms


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError(
                "EMBEDDING_BACKEND=sentence-transformers requires: pip install sentence-transformers"
            ) from e
        self.name = f"sentence-transformers:{model_name}"
        self._model = SentenceTransformer(model_name)

    def fit(self, texts: list[str]) -> None:  # neural model needs no fitting
        return None

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False,
                                  batch_size=32)
        return np.asarray(vecs, dtype=np.float32)


def get_embedder(backend: str, model_name: str) -> Embedder:
    if backend == "hashing":
        return HashingEmbedder()
    if backend in {"sentence-transformers", "sentence_transformers"}:
        return SentenceTransformerEmbedder(model_name)
    raise ValueError(f"Unknown EMBEDDING_BACKEND {backend!r} (use 'hashing' or 'sentence-transformers')")
