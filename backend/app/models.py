"""Plain dataclasses shared across modules (no web framework needed to use them)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RepoFile:
    path: str          # posix path relative to repo root
    language: str
    size: int          # bytes
    text: str

    @property
    def line_count(self) -> int:
        return self.text.count("\n") + (0 if self.text.endswith("\n") or not self.text else 1)


@dataclass
class Chunk:
    id: str                    # "path:start-end"
    path: str
    language: str
    kind: str                  # function | method | class | module | block
    name: str                  # qualified name, e.g. "Cart.total"; "" for blocks
    start_line: int            # 1-based, inclusive
    end_line: int
    text: str                  # exact source text of the chunk
    docstring: str = ""
    calls: list[str] = field(default_factory=list)  # simple names of functions called inside

    def embedding_text(self) -> str:
        """What we embed: location + name + docstring + code. Path/name words help retrieval."""
        return f"{self.path}\n{self.kind} {self.name}\n{self.docstring}\n{self.text}"


@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float
    reasons: list[str]


@dataclass
class TestOutcome:
    id: str
    status: str   # passed | failed | error | skipped
    message: str = ""


@dataclass
class TestRunResult:
    ran: bool                       # False => tests could not be executed at all
    outcomes: list[TestOutcome] = field(default_factory=list)
    exit_code: int | None = None
    duration_s: float = 0.0
    output_tail: str = ""
    error: str = ""                 # why it could not run (timeout, docker missing, ...)

    def count(self, status: str) -> int:
        return sum(1 for o in self.outcomes if o.status == status)
