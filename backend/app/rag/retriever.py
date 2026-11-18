"""Finding the code that is relevant to an issue.

Pipeline:  embed the issue -> vector search -> re-rank with "hints" from the issue text ->
add the functions that the best matches call.

Hints are cheap, high-precision signals a human would use too:
  * a stack trace line  ->  File "pkg/mod.py", line 42   (path + line number)
  * a file path          ->  pkg/mod.py
  * identifiers          ->  `Cart.total`, paginate(...)
Each boost is recorded as a human-readable "reason", which the UI shows as evidence.
"""
from __future__ import annotations

import builtins
import re
from dataclasses import dataclass, field

from ..models import Chunk, RetrievedChunk
from ..repo.analyzer import is_test_path
from .embeddings import Embedder
from .vector_store import VectorStore

_TRACE_RE = re.compile(r'File "([^"]+)", line (\d+)')
_PATH_RE = re.compile(r"([\w./\\-]+\.(?:py|js|jsx|ts|tsx|java|go|rs|rb|php|c|h|cpp|hpp|cs|kt|swift))(?::(\d+))?")
_BACKTICK_RE = re.compile(r"`([^`\n]{1,80})`")
_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\(")
_BUILTINS = set(dir(builtins))

PATH_BOOST = 0.30
LINE_BOOST = 0.45
IDENT_NAME_BOOST = 0.35
IDENT_TEXT_BOOST = 0.08
TEST_PENALTY = 0.8
DOC_PENALTY = 0.6          # README / config / text files rarely hold the bug
CALLEE_FACTOR = 0.6
BODY_WEIGHT, SYMBOL_WEIGHT = 0.6, 0.4  # similarity of code body vs. of name+path+docstring


@dataclass
class Hints:
    files: list[str] = field(default_factory=list)
    lines: list[tuple[str, int]] = field(default_factory=list)
    identifiers: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"files": self.files, "lines": [f"{p}:{n}" for p, n in self.lines],
                "identifiers": self.identifiers}


def extract_hints(issue: str) -> Hints:
    h = Hints()
    seen_files: set[str] = set()

    def add_file(p: str) -> str:
        p = p.replace("\\", "/")
        while p.startswith("./"):
            p = p[2:]
        if p and p not in seen_files:
            seen_files.add(p)
            h.files.append(p)
        return p

    for m in _TRACE_RE.finditer(issue):
        p = add_file(m.group(1))
        h.lines.append((p, int(m.group(2))))
    for m in _PATH_RE.finditer(issue):
        p = add_file(m.group(1))
        if m.group(2):
            h.lines.append((p, int(m.group(2))))

    idents: list[str] = []
    for m in _BACKTICK_RE.finditer(issue):
        inner = m.group(1).strip()
        mm = re.match(r"([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)", inner)
        if mm:
            idents.append(mm.group(1))
    idents.extend(m.group(1) for m in _CALL_RE.finditer(issue))
    seen: set[str] = set()
    for i in idents:
        if i in seen or i in _BUILTINS or len(i) < 3:
            continue
        if "." in i and i.split(".")[-1] in {"py", "js", "ts", "java", "go"}:
            continue  # it's a filename, not an identifier
        seen.add(i)
        h.identifiers.append(i)
    return h


def _path_matches(chunk_path: str, hint_path: str) -> bool:
    return (chunk_path == hint_path or hint_path.endswith("/" + chunk_path)
            or chunk_path.endswith("/" + hint_path))


def _name_matches(chunk: Chunk, ident: str) -> bool:
    if not chunk.name:
        return False
    return chunk.name == ident or chunk.name.split(".")[-1] == ident.split(".")[-1] and (
        "." not in ident or chunk.name.endswith(ident))


def _word_in(text: str, word: str) -> bool:
    return re.search(r"\b" + re.escape(word.split(".")[-1]) + r"\b", text) is not None


def _symbol_text(c: Chunk) -> str:
    """Short 'label' for a chunk: where it lives, what it is called, what its docstring says."""
    return f"{c.path} {c.name} {c.docstring}"


class CodeIndex:
    """Chunks + their embeddings + search.

    Each chunk gets TWO vectors: one for its full code body and one for its short label
    (path + name + docstring). A symptom like "word counter is wrong" matches the label of
    `count_words` even when its body is dominated by unrelated tokens.
    """

    def __init__(self, chunks: list[Chunk], embedder: Embedder):
        self.chunks = chunks
        self.embedder = embedder
        self.body_store: VectorStore[Chunk] = VectorStore()
        self.symbol_store: VectorStore[Chunk] = VectorStore()
        body_texts = [c.embedding_text() for c in chunks]
        symbol_texts = [_symbol_text(c) for c in chunks]
        embedder.fit(body_texts + symbol_texts)
        if chunks:
            self.body_store.add(embedder.embed(body_texts), chunks)
            self.symbol_store.add(embedder.embed(symbol_texts), chunks)
        # simple-name -> chunks, used to follow calls (only unambiguous names are followed)
        self._defs: dict[str, list[Chunk]] = {}
        for c in chunks:
            if c.kind in {"function", "method"} and not is_test_path(c.path):
                self._defs.setdefault(c.name.split(".")[-1], []).append(c)

    def retrieve(self, issue: str, k: int = 8, hints: Hints | None = None,
                 max_callees: int = 4) -> list[RetrievedChunk]:
        if not self.chunks:
            return []
        hints = hints or extract_hints(issue)
        qvec = self.embedder.embed([issue])[0]
        combined = (BODY_WEIGHT * self.body_store.scores(qvec)
                    + SYMBOL_WEIGHT * self.symbol_store.scores(qvec))
        order = combined.argsort()[::-1][: max(k * 5, 40)]
        scored: list[RetrievedChunk] = []
        for i in order:
            chunk, dense = self.chunks[int(i)], float(combined[i])
            score, reasons = dense, [f"semantic similarity {dense:.2f}"]
            for hp in hints.files:
                if _path_matches(chunk.path, hp):
                    score += PATH_BOOST
                    reasons.append(f"file {hp} is mentioned in the issue")
                    break
            for hp, line in hints.lines:
                if _path_matches(chunk.path, hp) and chunk.start_line <= line <= chunk.end_line:
                    score += LINE_BOOST
                    reasons.append(f"stack-trace line {hp}:{line} falls inside this code")
                    break
            for ident in hints.identifiers:
                if _name_matches(chunk, ident):
                    score += IDENT_NAME_BOOST
                    reasons.append(f"defines `{ident}`, which the issue mentions")
                    break
                if _word_in(chunk.text, ident):
                    score += IDENT_TEXT_BOOST
                    reasons.append(f"references `{ident}`, which the issue mentions")
                    break
            if is_test_path(chunk.path):
                score *= TEST_PENALTY
                reasons.append("test code (down-weighted)")
            elif chunk.language in {"markdown", "config", "text"}:
                score *= DOC_PENALTY
                reasons.append("documentation/config (down-weighted)")
            scored.append(RetrievedChunk(chunk, score, reasons))
        scored.sort(key=lambda r: -r.score)
        top = scored[:k]

        # Follow calls (up to 2 hops): the bug is often in a helper that a best match calls,
        # or in a helper of that helper. Only unambiguous function names are followed.
        have = {r.chunk.id for r in top}
        extra: list[RetrievedChunk] = []
        frontier = [(r, 1) for r in top if not is_test_path(r.chunk.path)][:3]
        while frontier and len(extra) < max_callees:
            parent, depth = frontier.pop(0)
            for callee_name in parent.chunk.calls:
                defs = self._defs.get(callee_name, [])
                if len(defs) != 1 or defs[0].id in have or len(extra) >= max_callees:
                    continue
                have.add(defs[0].id)
                label = parent.chunk.name or parent.chunk.path
                hop = RetrievedChunk(defs[0], parent.score * CALLEE_FACTOR,
                                     [f"called by `{label}`" + (" (a top match)" if depth == 1
                                                               else " (call chain from a top match)")])
                extra.append(hop)
                if depth < 2:
                    frontier.append((hop, depth + 1))
        return top + extra


def rank_files(retrieved: list[RetrievedChunk], limit: int = 6) -> list[dict]:
    """Aggregate chunk scores per file -> 'most relevant files' list."""
    agg: dict[str, dict] = {}
    for r in retrieved:
        e = agg.setdefault(r.chunk.path, {"path": r.chunk.path, "score": 0.0, "chunks": 0})
        e["score"] += r.score
        e["chunks"] += 1
    rows = sorted(agg.values(), key=lambda e: -e["score"])[:limit]
    for e in rows:
        e["score"] = round(e["score"], 3)
    return rows
