"""Fetching repositories safely.

Security stance: repository content is UNTRUSTED. In this module we only *read and copy* it.
We never import, build or execute anything from it. (Running tests happens in sandbox.py,
inside a locked-down Docker container.)

Hardening done while cloning:
  * Only https://github.com/<owner>/<repo> URLs are accepted (no file://, ssh://, other hosts),
    so a user cannot make the server read local paths or call internal network addresses.
  * git hooks are disabled (core.hooksPath=/dev/null) and symlinks are not created
    (core.symlinks=false); any symlink that still shows up is deleted.
  * Shallow clone (depth 1), with a timeout, and a hard size limit afterwards.
  * The .git folder is removed from the working copy.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from ..config import SAMPLES_DIR, Settings
from ..models import RepoFile

GITHUB_RE = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
SAMPLE_RE = re.compile(r"^sample:([A-Za-z0-9_-]+)$")

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "venv", ".venv", "env", "__pycache__", ".tox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build", "site-packages",
    "vendor", ".idea", ".vscode", ".next", "target", "coverage", ".eggs",
}

LANGUAGE_BY_EXT = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".java": "java", ".go": "go", ".rs": "rust", ".rb": "ruby",
    ".php": "php", ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cs": "csharp",
    ".kt": "kotlin", ".swift": "swift", ".sh": "shell", ".md": "markdown",
    ".toml": "config", ".cfg": "config", ".ini": "config", ".yaml": "config", ".yml": "config",
    ".json": "config", ".txt": "text",
}
# Languages whose *code* we index and reason about (markdown/config are indexed as plain text).
CODE_LANGUAGES = {
    "python", "javascript", "typescript", "java", "go", "rust", "ruby", "php", "c", "cpp",
    "csharp", "kotlin", "swift", "shell",
}


class RepoError(Exception):
    """A problem with the repository the user can understand and fix (bad URL, too big, ...)."""


def parse_github_url(url: str) -> tuple[str, str]:
    m = GITHUB_RE.match((url or "").strip())
    if not m:
        raise RepoError(
            "Only public GitHub repository URLs of the form https://github.com/<owner>/<repo> "
            "are supported."
        )
    return m.group(1), m.group(2)


def resolve_repo_ref(ref: str) -> tuple[str, str]:
    """Return ("github", url) or ("sample", name) or raise RepoError."""
    ref = (ref or "").strip()
    m = SAMPLE_RE.match(ref)
    if m:
        name = m.group(1)
        if not (SAMPLES_DIR / name).is_dir():
            raise RepoError(f"Unknown sample repository {name!r}.")
        return "sample", name
    parse_github_url(ref)
    return "github", ref


def _dir_size_bytes(root: Path) -> int:
    total = 0
    for dirpath, _dirs, files in os.walk(root, followlinks=False):
        for f in files:
            p = os.path.join(dirpath, f)
            try:
                if not os.path.islink(p):
                    total += os.path.getsize(p)
            except OSError:
                pass
    return total


def sanitize_tree(root: Path, settings: Settings) -> None:
    """Remove .git and symlinks, then enforce the total size limit."""
    shutil.rmtree(root / ".git", ignore_errors=True)
    for dirpath, dirs, files in os.walk(root, followlinks=False):
        for name in list(dirs) + list(files):
            p = Path(dirpath) / name
            if p.is_symlink():
                p.unlink()
        dirs[:] = [d for d in dirs if not (Path(dirpath) / d).is_symlink()]
    size = _dir_size_bytes(root)
    if size > settings.max_repo_mb * 1024 * 1024:
        raise RepoError(
            f"Repository is {size / 1024 / 1024:.0f} MB which exceeds the "
            f"{settings.max_repo_mb} MB limit (MAX_REPO_MB)."
        )


def _run_git_clone(url: str, dest: Path, settings: Settings) -> None:
    """Shallow, hook-free, symlink-free clone. Raises RepoError on any failure."""
    if shutil.which("git") is None:
        raise RepoError("git is not installed on the server, cannot clone repositories.")
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}
    cmd = [
        "git", "-c", "core.hooksPath=/dev/null", "-c", "core.symlinks=false",
        "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never",
        "clone", "--depth", "1", "--single-branch", "--no-tags", "--", url, str(dest),
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=settings.clone_timeout_s, env=env
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(dest, ignore_errors=True)
        raise RepoError(f"Cloning timed out after {settings.clone_timeout_s}s (repository too large?).")
    if proc.returncode != 0:
        shutil.rmtree(dest, ignore_errors=True)
        tail = (proc.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
        raise RepoError(f"git clone failed (is the repository public and the URL correct?): {tail[0]}")


def clone_github(url: str, dest: Path, settings: Settings) -> Path:
    parse_github_url(url)  # validates; raises RepoError
    _run_git_clone(url, dest, settings)
    try:
        sanitize_tree(dest, settings)
    except RepoError:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return dest


def copy_local_tree(src: Path, dest: Path, settings: Settings) -> Path:
    """Copy a trusted-by-us local directory (bundled samples, tests). Never exposed to web input."""
    shutil.copytree(src, dest, symlinks=False, ignore=shutil.ignore_patterns("__pycache__", ".git"))
    sanitize_tree(dest, settings)
    return dest


def load_repo(ref: str, dest: Path, settings: Settings) -> Path:
    kind, value = resolve_repo_ref(ref)
    if kind == "sample":
        return copy_local_tree(SAMPLES_DIR / value, dest, settings)
    return clone_github(value, dest, settings)


def _looks_binary(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return b"\x00" in fh.read(2048)
    except OSError:
        return True


def iter_source_files(root: Path, settings: Settings) -> tuple[list[RepoFile], list[str]]:
    """Walk the repo and return (files, warnings). Skips junk dirs, binaries, huge files."""
    files: list[RepoFile] = []
    warnings: list[str] = []
    skipped_big = 0
    max_bytes = settings.max_file_kb * 1024
    for dirpath, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith(".git"))
        for name in sorted(names):
            p = Path(dirpath) / name
            lang = LANGUAGE_BY_EXT.get(p.suffix.lower())
            if lang is None or p.is_symlink():
                continue
            try:
                size = p.stat().st_size
            except OSError:
                continue
            if size > max_bytes:
                skipped_big += 1
                continue
            if _looks_binary(p):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            files.append(RepoFile(path=p.relative_to(root).as_posix(), language=lang, size=size, text=text))
            if len(files) >= settings.max_files_indexed:
                warnings.append(
                    f"Stopped after {settings.max_files_indexed} files (MAX_FILES_INDEXED); "
                    "the rest of the repository was not indexed."
                )
                return files, warnings
    if skipped_big:
        warnings.append(f"Skipped {skipped_big} file(s) larger than {settings.max_file_kb} KB.")
    return files, warnings
