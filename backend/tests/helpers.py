"""Test helpers (test doubles). Nothing in here is used by the real application."""
from __future__ import annotations

import dataclasses
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from app.config import Settings
from app.models import TestOutcome, TestRunResult


def make_symlink(link, target, target_is_directory: bool = False) -> bool:
    """Try to create a symlink; return False if this machine does not allow it.

    On Windows, creating symlinks needs Administrator rights or Developer Mode, otherwise Python
    raises OSError (WinError 1314). Tests that need a REAL symlink call this and skip only that
    part when it returns False."""
    try:
        os.symlink(target, link, target_is_directory=target_is_directory)
        return True
    except (OSError, NotImplementedError):
        return False


def make_settings(tmp: Path | None = None, **overrides) -> Settings:
    base = Settings(workspace_dir=Path(tmp) if tmp else Path(tempfile.mkdtemp(prefix="cpx-test-")))
    return dataclasses.replace(base, **overrides)


class ScriptedLLM:
    """Test double: returns pre-written replies in order and records the prompts it received.
    It is NOT a model -- it only lets us test the pipeline plumbing deterministically."""
    model = "scripted-test-double"

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self.replies:
            raise AssertionError("ScriptedLLM ran out of replies")
        return self.replies.pop(0)


_V = re.compile(r"^(?P<name>\S+) \((?P<mod>[\w.]+)\)(?:\n.*?)? \.\.\. (?P<res>ok|FAIL|ERROR|skipped.*)$",
                re.MULTILINE)


class TrustedLocalRunner:
    """TEST DOUBLE ONLY. Runs unittest on our OWN bundled sample repos directly on the host, so
    the pipeline's before/after logic can be exercised with real test execution inside the unit
    tests. It is never used by the application: the real app only ever uses DockerSandbox, and
    it does not fall back to running on the host. Never point this at untrusted code."""

    def availability(self):
        return True, "ok"

    def run_tests(self, workdir: Path, targets: list[str]) -> TestRunResult:
        outcomes: list[TestOutcome] = []
        tails = []
        env = {**os.environ, "PYTHONPATH": f"{workdir}:{workdir}/src", "PYTHONDONTWRITEBYTECODE": "1"}
        for t in targets:
            p = Path(workdir) / t
            args = [sys.executable, "-m", "unittest", "discover", "-v"]
            args += ["-s", str(p.parent), "-p", p.name] if p.is_file() else ["-s", str(p)]
            proc = subprocess.run(args, cwd=workdir, env=env, capture_output=True, text=True, timeout=60)
            text = proc.stderr
            tails.append(text[-1500:])
            for m in _V.finditer(text):
                mod = m.group("mod")
                res = m.group("res")
                broken = "_FailedTest" in mod
                status = ("passed" if res == "ok" else "skipped" if res.startswith("skipped")
                          else "error" if broken else "failed")  # pytest reports test-body exceptions as failures
                outcomes.append(TestOutcome(id=f"{mod}::{m.group('name')}", status=status))
        return TestRunResult(ran=True, outcomes=outcomes, exit_code=0, output_tail="\n".join(tails)[-3000:])
