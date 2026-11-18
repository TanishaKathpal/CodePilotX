"""Understanding a repository: structure summary + splitting code into searchable chunks.

Why chunk by function instead of fixed-size text windows?
  Bugs live in functions. If we cut code at arbitrary line counts we may split the buggy
  function in half, and the embedding of each half is blurry. For Python we use the standard
  library `ast` module to get exact function/method/class boundaries. For other languages we
  fall back to overlapping line windows (works, but is less precise).
"""
from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict

from ..models import Chunk, RepoFile

WINDOW_LINES = 60
WINDOW_OVERLAP = 10
MAX_FUNCTION_LINES = 120  # longer functions are split into windows

KEY_FILE_PATTERNS = re.compile(
    r"^(readme(\.\w+)?|pyproject\.toml|setup\.py|setup\.cfg|requirements[\w.-]*\.txt|pytest\.ini|"
    r"tox\.ini|package\.json|makefile|dockerfile|go\.mod|cargo\.toml|pom\.xml)$",
    re.IGNORECASE,
)
TEST_FILE_RE = re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.py|conftest\.py)$")
TEST_DIR_NAMES = {"tests", "test"}


def is_test_path(path: str) -> bool:
    """True for paths that look like tests. The patch applier refuses to edit these."""
    parts = path.split("/")
    return bool(TEST_FILE_RE.search(path)) or any(p in TEST_DIR_NAMES for p in parts[:-1])


# --------------------------------------------------------------------------- chunking

def _window_chunks(f: RepoFile, start: int = 1, end: int | None = None, kind="block", name="") -> list[Chunk]:
    lines = f.text.splitlines()
    end = end or len(lines)
    out: list[Chunk] = []
    pos = start
    step = WINDOW_LINES - WINDOW_OVERLAP
    while pos <= end:
        stop = min(pos + WINDOW_LINES - 1, end)
        text = "\n".join(lines[pos - 1:stop])
        if text.strip():
            out.append(Chunk(id=f"{f.path}:{pos}-{stop}", path=f.path, language=f.language, kind=kind,
                             name=name, start_line=pos, end_line=stop, text=text))
        if stop >= end:
            break
        pos += step
    return out


def _called_names(node: ast.AST) -> list[str]:
    names: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            fn = sub.func
            if isinstance(fn, ast.Name):
                names.append(fn.id)
            elif isinstance(fn, ast.Attribute):
                names.append(fn.attr)
    return sorted(set(names))


def _node_start(node) -> int:
    decos = getattr(node, "decorator_list", [])
    return min([node.lineno] + [d.lineno for d in decos])


def chunk_python(f: RepoFile) -> list[Chunk]:
    try:
        tree = ast.parse(f.text)
    except (SyntaxError, ValueError):
        return _window_chunks(f)  # unparsable (e.g. Python 2) -> generic windows
    lines = f.text.splitlines()
    chunks: list[Chunk] = []
    covered: set[int] = set()

    def add(node, qualname: str, kind: str) -> None:
        start, end = _node_start(node), node.end_lineno or node.lineno
        covered.update(range(start, end + 1))
        doc = ast.get_docstring(node) or ""
        calls = _called_names(node)
        if end - start + 1 > MAX_FUNCTION_LINES:
            for c in _window_chunks(f, start, end, kind=kind, name=qualname):
                c.docstring, c.calls = doc, calls
                chunks.append(c)
            return
        chunks.append(Chunk(
            id=f"{f.path}:{start}-{end}", path=f.path, language="python", kind=kind, name=qualname,
            start_line=start, end_line=end, text="\n".join(lines[start - 1:end]),
            docstring=doc, calls=calls))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add(node, node.name, "function")
        elif isinstance(node, ast.ClassDef):
            methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            for m in methods:
                add(m, f"{node.name}.{m.name}", "method")
            # class header: from the `class` line up to the first method (docstring + attributes)
            c_start = _node_start(node)
            c_end = (min(_node_start(m) for m in methods) - 1) if methods else (node.end_lineno or node.lineno)
            if c_end >= c_start:
                text = "\n".join(lines[c_start - 1:c_end])
                if text.strip():
                    covered.update(range(c_start, c_end + 1))
                    chunks.append(Chunk(
                        id=f"{f.path}:{c_start}-{c_end}", path=f.path, language="python", kind="class",
                        name=node.name, start_line=c_start, end_line=c_end, text=text,
                        docstring=ast.get_docstring(node) or ""))
    # module-level statements (imports, constants, scripts) -> grouped into module chunks
    run_start = None
    for ln in range(1, len(lines) + 2):
        free = ln <= len(lines) and ln not in covered
        if free and run_start is None:
            run_start = ln
        elif not free and run_start is not None:
            text = "\n".join(lines[run_start - 1:ln - 1])
            if text.strip():
                for c in _window_chunks(f, run_start, ln - 1, kind="module", name=""):
                    chunks.append(c)
            run_start = None
    chunks.sort(key=lambda c: (c.start_line, c.end_line))
    return chunks


def chunk_file(f: RepoFile) -> list[Chunk]:
    if f.language == "python":
        return chunk_python(f)
    return _window_chunks(f)


def chunk_repo(files: list[RepoFile]) -> list[Chunk]:
    out: list[Chunk] = []
    for f in files:
        out.extend(chunk_file(f))
    return out


# --------------------------------------------------------------------------- summary

def _tree_overview(files: list[RepoFile], depth: int = 2, max_entries: int = 40) -> list[dict]:
    """Top-level folder overview: [{path, files, lines}], limited for display."""
    agg: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for f in files:
        parts = f.path.split("/")
        key = "/".join(parts[:depth]) + ("/" if len(parts) > depth else "")
        if len(parts) <= depth - 1 or len(parts) == 1:
            key = f.path
        agg[key][0] += 1
        agg[key][1] += f.line_count
    rows = [{"path": k, "files": v[0], "lines": v[1]} for k, v in sorted(agg.items())]
    return rows[:max_entries]


def detect_test_targets(files: list[RepoFile]) -> list[str]:
    """Which paths to hand to pytest: a top-level tests/ dir if present, plus stray test files."""
    py = [f.path for f in files if f.language == "python" and TEST_FILE_RE.search(f.path)
          and not f.path.endswith("conftest.py")]
    targets: list[str] = []
    for d in ("tests", "test"):
        if any(p.startswith(d + "/") for p in py):
            targets.append(d)
    rest = [p for p in py if not any(p.startswith(t + "/") for t in targets)]
    targets.extend(rest[:50])
    return targets


def summarize_repo(files: list[RepoFile], chunks: list[Chunk], warnings: list[str] | None = None) -> dict:
    langs: dict[str, dict] = {}
    counter_files = Counter(f.language for f in files)
    for lang, n in counter_files.items():
        langs[lang] = {"files": n, "lines": sum(f.line_count for f in files if f.language == lang)}
    code_langs = {k: v for k, v in langs.items() if k not in {"markdown", "config", "text"}}
    primary = max(code_langs, key=lambda k: code_langs[k]["lines"]) if code_langs else None

    key_files = [f.path for f in files if KEY_FILE_PATTERNS.match(f.path.split("/")[-1])][:15]
    entry_points = [f.path for f in files if f.language == "python" and "__main__" in f.text
                    and re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]", f.text)
                    and not TEST_FILE_RE.search(f.path)][:10]
    symbols = [c for c in chunks if c.kind in {"function", "method", "class"} and not is_test_path(c.path)]
    test_targets = detect_test_targets(files)
    deps_text = " ".join(f.text.lower() for f in files if f.path.split("/")[-1] in
                         {"requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "tox.ini"})
    notes: list[str] = list(warnings or [])
    if primary and primary != "python":
        notes.append(
            f"Primary language is {primary}. Retrieval and diagnosis work with generic text chunks, "
            "but automated test execution is only supported for Python (pytest)."
        )
    if "python" in code_langs and not test_targets:
        notes.append("No existing Python tests were found; only the generated test will be run.")
    if re.search(r"(numpy|pandas|django|flask|torch|requests|scipy)", deps_text):
        notes.append(
            "The repository declares third-party dependencies. The default sandbox has no network and "
            "only pytest installed, so tests importing them may fail to run (see README, 'Sandbox image')."
        )
    return {
        "file_count": len(files),
        "line_count": sum(f.line_count for f in files),
        "languages": langs,
        "primary_language": primary,
        "key_files": key_files,
        "entry_points": entry_points,
        "structure": _tree_overview(files),
        "symbol_count": len(symbols),
        "chunk_count": len(chunks),
        "test_targets": test_targets,
        "has_pytest_dependency": "pytest" in deps_text,
        "validation_supported": primary == "python",
        "notes": notes,
    }
