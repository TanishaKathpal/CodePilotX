import ntpath
import os
import posixpath
import shutil
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest import mock

from app.models import TestOutcome as Outcome, TestRunResult as RunResult
from app.sandbox import DockerSandbox, _bind_mount, build_docker_command, parse_junit
from app.validation import GENERATED_FILE, judge
from tests.helpers import make_settings

JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="1" failures="1" skipped="1" tests="4">
<testcase classname="tests.test_a" name="test_ok" time="0.001"/>
<testcase classname="tests.test_a" name="test_bad" time="0.001"><failure message="assert 1 == 2">trace</failure></testcase>
<testcase classname="" name="codepilotx_generated.test_codepilotx_generated" time="0"><error message="collection failure">ImportError</error></testcase>
<testcase classname="tests.test_a" name="test_skip"><skipped message="why"/></testcase>
</testsuite></testsuites>"""


class DockerCommandTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp(prefix="cpx-cmd-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        # Real, absolute directories: the host path format differs per OS (/tmp/x vs C:\\Users\\x),
        # so tests must compute expectations from the real path instead of hard-coding "/w".
        self.work, self.out = (tmp / "work").resolve(), (tmp / "out").resolve()
        self.work.mkdir()
        self.out.mkdir()
        self.cmd = build_docker_command(make_settings(), self.work, self.out, "cpx-1", ["tests", "-evil.py"])

    def has_pair(self, a, b):
        return any(self.cmd[i] == a and self.cmd[i + 1] == b for i in range(len(self.cmd) - 1))

    def test_isolation_flags_present(self):
        self.assertTrue(self.has_pair("--network", "none"))
        self.assertIn("--read-only", self.cmd)
        self.assertTrue(self.has_pair("--cap-drop", "ALL"))
        self.assertTrue(self.has_pair("--security-opt", "no-new-privileges"))
        self.assertTrue(self.has_pair("--user", "65534:65534"))
        self.assertTrue(self.has_pair("--memory", "512m"))
        self.assertTrue(self.has_pair("--memory-swap", "512m"))
        self.assertTrue(self.has_pair("--pids-limit", "128"))
        self.assertTrue(self.has_pair("--cpus", "1.0"))
        self.assertIn("--rm", self.cmd)

    def test_only_expected_mounts_and_no_host_leaks(self):
        mounts = [self.cmd[i + 1] for i, c in enumerate(self.cmd) if c == "-v"]
        self.assertEqual(len(mounts), 2)  # exactly two bind mounts, nothing else from the host
        # Each spec is "<native host path>:<container path>:rw". Parse from the right so a Windows
        # drive letter ("C:\\...") on the left does not confuse the split.
        parsed = [m.rsplit(":", 2) for m in mounts]
        self.assertEqual([p[1:] for p in parsed], [["/work", "rw"], ["/out", "rw"]])
        self.assertEqual(parsed[0][0], str(self.work))   # platform-native form, e.g. C:\\... on Windows
        self.assertEqual(parsed[1][0], str(self.out))
        self.assertNotIn("--privileged", self.cmd)
        self.assertFalse(any("docker.sock" in c for c in self.cmd))
        self.assertNotIn("--network=host", self.cmd)

    def test_targets_come_after_double_dash(self):
        i = self.cmd.index("--")
        self.assertEqual(self.cmd[i + 1:], ["tests", "-evil.py"])
        self.assertLess(self.cmd.index("--junitxml=/out/junit.xml"), i)


class BindMountValidationTests(unittest.TestCase):
    def test_posix_path_format(self):
        posix_path = PurePosixPath("/srv/jobs/job-1")
        with mock.patch("os.path.isabs", posixpath.isabs):
            self.assertEqual(
                _bind_mount(posix_path, "/work"),
                "/srv/jobs/job-1:/work:rw"
            )

    def test_windows_drive_path_is_accepted_in_native_form(self):
        # Simulates Windows on any OS: Windows' own isabs() rules, backslash path, drive-letter colon.
        win = Path(r"C:\Users\me\codepilotx\.workspace\job-1")
        with mock.patch("os.path.isabs", ntpath.isabs):
            self.assertEqual(_bind_mount(win, "/work"), str(win) + ":/work:rw")

    def test_rejects_paths_that_could_change_the_mount_spec(self):
        bad_cases = [
            (posixpath.isabs, "/srv/a:/etc"),             # extra colon -> would add/alter fields
            (posixpath.isabs, "/srv/a:ro"),
            (ntpath.isabs, r"C:\jobs\a:b"),              # colon after the drive letter
            (posixpath.isabs, "/srv/a\nb"),               # newline
            (posixpath.isabs, "relative/path"),           # must be absolute
        ]
        for isabs, text in bad_cases:
            with self.subTest(path=text), mock.patch("os.path.isabs", isabs):
                with self.assertRaises(ValueError):
                    _bind_mount(Path(text), "/work")

    @unittest.skipUnless(os.name == "posix", "needs a directory name containing ':' (not allowed on Windows)")
    def test_run_tests_refuses_unsafe_workspace_without_starting_docker(self):
        base = Path(tempfile.mkdtemp(prefix="cpx-unsafe-"))
        self.addCleanup(shutil.rmtree, base, True)
        weird = base / "ws:evil"
        weird.mkdir()
        (base / "work").mkdir()
        sandbox = DockerSandbox(make_settings(weird))
        with mock.patch.object(DockerSandbox, "availability", return_value=(True, "ok")), \
                mock.patch("subprocess.run") as run:
            res = sandbox.run_tests(base / "work", ["tests"])
        self.assertFalse(res.ran)
        self.assertIn("Refusing", res.error)
        run.assert_not_called()


class JunitTests(unittest.TestCase):
    def test_parse(self):
        out = {o.id: o for o in parse_junit(JUNIT)}
        self.assertEqual(out["tests.test_a::test_ok"].status, "passed")
        self.assertEqual(out["tests.test_a::test_bad"].status, "failed")
        self.assertIn("assert 1 == 2", out["tests.test_a::test_bad"].message)
        self.assertEqual(out["codepilotx_generated.test_codepilotx_generated"].status, "error")
        self.assertEqual(out["tests.test_a::test_skip"].status, "skipped")

    def test_rejects_xml_bombs_and_oversize(self):
        bomb = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><testsuites>&a;</testsuites>'
        with self.assertRaises(ValueError):
            parse_junit(bomb)
        with self.assertRaises(ValueError):
            parse_junit("<a>" + "x" * (6 * 1024 * 1024) + "</a>")

    def test_garbage(self):
        import xml.etree.ElementTree as ET
        with self.assertRaises(ET.ParseError):
            parse_junit("not xml")


class UnavailableDockerTests(unittest.TestCase):
    def test_no_docker_means_not_run_and_never_host_fallback(self):
        with mock.patch("shutil.which", return_value=None), mock.patch("subprocess.run") as run:
            res = DockerSandbox(make_settings()).run_tests(Path(tempfile.mkdtemp()), ["tests"])
        self.assertFalse(res.ran)
        self.assertIn("Docker", res.error)
        run.assert_not_called()  # nothing at all was executed

    def test_daemon_down(self):
        fake = mock.Mock(returncode=1, stdout="", stderr="")
        with mock.patch("shutil.which", return_value="/usr/bin/docker"), mock.patch("subprocess.run", return_value=fake):
            ok, why = DockerSandbox(make_settings()).availability()
        self.assertFalse(ok)
        self.assertIn("daemon", why)

    @unittest.skipIf(shutil.which("docker"), "docker present on this machine")
    def test_real_environment_without_docker(self):
        ok, why = DockerSandbox(make_settings()).availability()
        self.assertFalse(ok)


def run(*pairs, ran=True, error=""):
    return RunResult(ran=ran, outcomes=[Outcome(i, s, f"msg-{i}") for i, s in pairs], error=error)


G = "codepilotx_generated.test_codepilotx_generated::test_bug"
E1, E2 = "tests.test_a::test_one", "tests.test_a::test_two"


class JudgeTests(unittest.TestCase):
    def test_validated(self):
        v = judge(run((G, "failed"), (E1, "passed"), (E2, "passed")), run((G, "passed"), (E1, "passed"), (E2, "passed")))
        self.assertEqual(v.verdict, "validated")
        self.assertTrue(v.verified_fix and v.reproduced)

    def test_not_reproduced_when_test_already_passes(self):
        v = judge(run((G, "passed"), (E1, "passed")), run((G, "passed"), (E1, "passed")))
        self.assertEqual(v.verdict, "not_reproduced")
        self.assertFalse(v.verified_fix)

    def test_fix_failed(self):
        v = judge(run((G, "failed")), run((G, "failed")))
        self.assertEqual(v.verdict, "fix_failed")
        self.assertFalse(v.verified_fix)
        self.assertTrue(v.reproduced)

    def test_regression(self):
        v = judge(run((G, "failed"), (E1, "passed")), run((G, "passed"), (E1, "failed")))
        self.assertEqual(v.verdict, "regression")
        self.assertEqual(v.regressions, [E1])

    def test_regression_when_existing_test_disappears(self):
        v = judge(run((G, "failed"), (E1, "passed")), run((G, "passed")))
        self.assertEqual(v.verdict, "regression")

    def test_preexisting_failure_is_not_a_regression(self):
        v = judge(run((G, "failed"), (E1, "failed")), run((G, "passed"), (E1, "failed")))
        self.assertEqual(v.verdict, "validated")

    def test_skipped_generated_test_is_not_a_pass(self):
        v = judge(run((G, "failed")), run((G, "skipped")))
        self.assertEqual(v.verdict, "fix_failed")

    def test_broken_generated_test(self):
        self.assertEqual(judge(run((G, "error")), run((G, "passed"))).verdict, "test_error")
        self.assertEqual(judge(run((E1, "passed")), run((E1, "passed"))).verdict, "test_error")  # none collected

    def test_generated_file_missing_after_patch(self):
        self.assertEqual(judge(run((G, "failed")), run((E1, "passed"))).verdict, "fix_failed")

    def test_could_not_run(self):
        v = judge(run(ran=False, error="timeout"), run((G, "passed")))
        self.assertEqual(v.verdict, "run_error")
        self.assertIn("timeout", v.message)
        self.assertEqual(judge(run((G, "failed")), run(ran=False, error="oom")).verdict, "run_error")

    def test_generated_path_constant(self):
        self.assertIn("codepilotx_generated", GENERATED_FILE)


if __name__ == "__main__":
    unittest.main()
