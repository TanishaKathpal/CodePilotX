"""Deciding whether a fix is validated.

Rule of the project: *never claim a bug is fixed unless tests actually passed.*

We run the SAME test selection twice in the sandbox:
  BEFORE = original repository + the generated test
  AFTER  = patched  repository + the generated test
and compare. A fix is "validated" only if ALL of these hold:
  1. the generated test FAILED before  (so it really reproduces the bug -- a test that already
     passes proves nothing),
  2. every generated test PASSES after,
  3. no test that passed before fails after (no regressions).

Every other combination is reported with its own, more modest, verdict.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import TestRunResult

GENERATED_DIR = "codepilotx_generated"
GENERATED_FILE = f"{GENERATED_DIR}/test_codepilotx_generated.py"

VERDICT_LABELS = {
    "validated": "Validated - generated test failed before the fix and passes after it; no regressions",
    "not_reproduced": "Not validated - the generated test already passes on the original code",
    "fix_failed": "Not fixed - the generated test still fails after the change",
    "regression": "Not safe - the change breaks tests that passed before",
    "test_error": "Not validated - the generated test is broken (could not be collected/run)",
    "patch_failed": "Not validated - the proposed edit could not be applied to the code",
    "run_error": "Not validated - the tests could not be executed",
    "not_validated": "Not validated - automated test execution was not possible",
}


@dataclass
class Verdict:
    verdict: str
    message: str
    reproduced: bool = False
    regressions: list[str] = field(default_factory=list)

    @property
    def verified_fix(self) -> bool:
        return self.verdict == "validated"


def is_generated(test_id: str) -> bool:
    return GENERATED_DIR in test_id


def judge(before: TestRunResult, after: TestRunResult) -> Verdict:
    for label, res in (("original", before), ("patched", after)):
        if not res.ran:
            return Verdict("run_error", f"Tests could not run on the {label} code: {res.error}")

    gen_before = [o for o in before.outcomes if is_generated(o.id)]
    gen_after = [o for o in after.outcomes if is_generated(o.id)]
    if not gen_before:
        return Verdict("test_error", "No generated tests were collected on the original code "
                                     "(syntax or import problem in the generated test).")
    if any(o.status == "error" for o in gen_before) and not any(o.status == "failed" for o in gen_before):
        first = next(o for o in gen_before if o.status == "error")
        return Verdict("test_error", f"The generated test errored before running ({first.message[:200]}).")
    if not any(o.status == "failed" for o in gen_before):
        return Verdict("not_reproduced",
                       "The generated test passes even without the fix, so it does not demonstrate the bug.")

    bad_after = [o for o in gen_after if o.status != "passed"]
    if not gen_after or bad_after:
        detail = f" ({bad_after[0].id}: {bad_after[0].message[:160]})" if bad_after else ""
        return Verdict("fix_failed", f"The generated test still fails after applying the change{detail}.",
                       reproduced=True)

    passed_before = {o.id for o in before.outcomes if o.status == "passed" and not is_generated(o.id)}
    status_after = {o.id: o.status for o in after.outcomes}
    regressions = sorted(i for i in passed_before if status_after.get(i) != "passed")
    if regressions:
        return Verdict("regression",
                       f"{len(regressions)} previously passing test(s) fail after the change.",
                       reproduced=True, regressions=regressions)

    n_exist = len(passed_before)
    return Verdict(
        "validated",
        f"The generated test failed before the change and passes after it; "
        f"{n_exist} existing test(s) that passed before still pass.",
        reproduced=True)
