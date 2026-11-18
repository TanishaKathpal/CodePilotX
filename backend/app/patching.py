"""Applying the model's proposed edits safely.

The model returns edits as {file, search, replace}. Compared with unified diffs, exact
search/replace blocks are much more reliable for LLMs (they don't have to count line numbers).

Safety rules enforced here (the model is NOT trusted):
  * only EXISTING, regular, non-symlink files inside the repository copy can be edited;
  * no absolute paths, no `..`, nothing under .git;
  * test files and test/CI configuration cannot be edited -- otherwise a "fix" could simply
    weaken the tests that are supposed to judge it;
  * only source-code files are editable (not arbitrary data/binary files);
  * every `search` text must match exactly ONE place (a tolerant fallback ignores trailing
    whitespace differences only);
  * the operation is atomic: if any edit fails, nothing is written.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from .repo.analyzer import is_test_path
from .repo.loader import CODE_LANGUAGES, LANGUAGE_BY_EXT

PROTECTED_NAMES = {"conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml", "noxfile.py"}


class PatchError(Exception):
    """An edit could not be applied. The message is fed back to the model on retry."""


@dataclass
class PatchResult:
    files: dict[str, tuple[str, str]] = field(default_factory=dict)  # path -> (old, new)
    diff: str = ""


def _check_path(root: Path, rel: str) -> Path:
    if not rel or rel.startswith(("/", "\\")) or ":" in rel.split("/")[0] or "\\" in rel:
        raise PatchError(f"Invalid file path {rel!r}: use a relative POSIX path like 'pkg/module.py'.")
    parts = rel.split("/")
    if ".." in parts or ".git" in parts:
        raise PatchError(f"Path {rel!r} is not allowed.")
    p = (root / rel)
    try:
        resolved = p.resolve()
        resolved.relative_to(root.resolve())
    except (ValueError, OSError):
        raise PatchError(f"Path {rel!r} escapes the repository.")
    if p.is_symlink() or not p.is_file():
        raise PatchError(f"File {rel!r} does not exist in the repository (only existing files can be edited).")
    if is_test_path(rel) or parts[-1] in PROTECTED_NAMES:
        raise PatchError(f"Editing {rel!r} is not allowed: tests and test configuration must stay unchanged.")
    lang = LANGUAGE_BY_EXT.get(p.suffix.lower())
    if lang not in CODE_LANGUAGES:
        raise PatchError(f"Editing {rel!r} is not allowed: only source-code files can be edited.")
    return p


def _find_block(text: str, search: str) -> tuple[int, int]:
    """Locate `search` in `text` -> (start, end) char offsets. Must be unique."""
    n = text.count(search)
    if n == 1:
        i = text.index(search)
        if i > 0 and search[:1] in (" ", "\t") and text[i - 1] in (" ", "\t"):
            raise PatchError(
                "The 'search' text starts in the middle of a line's indentation. Copy the whole "
                "line including its full leading whitespace.")
        return i, i + len(search)
    if n > 1:
        raise PatchError(
            f"The 'search' text matches {n} places; include more surrounding lines so it is unique.")
    # Fallback: ignore trailing-whitespace differences line by line (indentation must still match).
    core = search.strip("\n")
    if not core:
        raise PatchError("The 'search' text is empty.")
    s_lines = [l.rstrip() for l in core.split("\n")]
    t_lines = text.split("\n")
    offsets, pos = [], 0
    for l in t_lines:
        offsets.append(pos)
        pos += len(l) + 1
    hits = [i for i in range(len(t_lines) - len(s_lines) + 1)
            if [x.rstrip() for x in t_lines[i:i + len(s_lines)]] == s_lines]
    if len(hits) == 1:
        i = hits[0]
        return offsets[i], offsets[i + len(s_lines) - 1] + len(t_lines[i + len(s_lines) - 1])
    if len(hits) > 1:
        raise PatchError("The 'search' text matches several places; include more surrounding lines.")
    raise PatchError(
        "The 'search' text was not found in the file. Copy it exactly from the provided source, "
        "including indentation.")


def apply_edits(root: Path, edits: list[dict]) -> PatchResult:
    """Apply edits to files under `root` (a throw-away copy). Atomic."""
    if not edits:
        raise PatchError("No edits were provided.")
    original: dict[str, str] = {}
    current: dict[str, str] = {}
    crlf: dict[str, bool] = {}
    for e in edits:
        rel = e["file"].strip()
        path = _check_path(root, rel)
        if rel not in current:
            try:
                raw = path.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                raise PatchError(f"File {rel!r} is not valid UTF-8 text.")
            crlf[rel] = "\r\n" in raw
            original[rel] = raw.replace("\r\n", "\n")
            current[rel] = original[rel]
        search = e["search"].replace("\r\n", "\n")
        replace = e["replace"].replace("\r\n", "\n")
        exact = current[rel].count(search) == 1
        start, end = _find_block(current[rel], search)
        if not exact:  # fuzzy match: keep the newline structure of what we matched
            replace = replace.strip("\n")
        current[rel] = current[rel][:start] + replace + current[rel][end:]
    result = PatchResult()
    diffs: list[str] = []
    for rel, new in current.items():
        old = original[rel]
        if new == old:
            raise PatchError(f"The edit to {rel!r} changes nothing.")
        diffs.append("\n".join(difflib.unified_diff(
            old.splitlines(), new.splitlines(), fromfile=f"a/{rel}", tofile=f"b/{rel}", lineterm="")))
        result.files[rel] = (old, new)
    # all edits validated -> now write (still inside the throw-away copy)
    for rel, (_old, new) in result.files.items():
        out = new.replace("\n", "\r\n") if crlf[rel] else new
        (root / rel).write_bytes(out.encode("utf-8"))
    result.diff = "\n".join(diffs)
    return result
