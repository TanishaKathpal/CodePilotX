import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.patching import PatchError, apply_edits
from tests.helpers import make_symlink

SRC = "def f(a):\n    x = a + 1\n    return x\n\n\ndef g(b):\n    x = b + 1\n    return x\n"


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "pkg").mkdir()
        (self.root / "pkg" / "m.py").write_text(SRC)
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_m.py").write_text("def test_x(): pass\n")
        (self.root / "data.json").write_text("{}")
        (self.root / "conftest.py").write_text("")
        self.addCleanup(self.tmp.cleanup)

    def edit(self, **kw):
        base = {"file": "pkg/m.py", "search": "    x = a + 1\n", "replace": "    x = a + 2\n"}
        return [{**base, **kw}]

    def test_exact_edit_and_diff(self):
        r = apply_edits(self.root, self.edit())
        self.assertIn("a + 2", (self.root / "pkg" / "m.py").read_text())
        self.assertIn("-    x = a + 1", r.diff)
        self.assertIn("+    x = a + 2", r.diff)
        self.assertIn("--- a/pkg/m.py", r.diff)

    def test_ambiguous_search_rejected_and_nothing_written(self):
        with self.assertRaises(PatchError) as cm:
            apply_edits(self.root, self.edit(search="    return x\n"))
        self.assertIn("2 places", str(cm.exception))
        self.assertEqual((self.root / "pkg" / "m.py").read_text(), SRC)

    def test_not_found(self):
        with self.assertRaises(PatchError) as cm:
            apply_edits(self.root, self.edit(search="nothing like this"))
        self.assertIn("not found", str(cm.exception))

    def test_trailing_whitespace_tolerated(self):
        apply_edits(self.root, self.edit(search="def f(a):   \n    x = a + 1   ", replace="def f(a):\n    x = a * 9"))
        self.assertIn("x = a * 9", (self.root / "pkg" / "m.py").read_text())
        self.assertIn("def g(b):", (self.root / "pkg" / "m.py").read_text())

    def test_indentation_mismatch_still_rejected(self):
        with self.assertRaises(PatchError):
            apply_edits(self.root, self.edit(search="x = a + 1\n"[0:0] + "  x = a + 1\n"))

    def test_atomic_across_edits(self):
        edits = self.edit() + self.edit(search="missing text")
        with self.assertRaises(PatchError):
            apply_edits(self.root, edits)
        self.assertEqual((self.root / "pkg" / "m.py").read_text(), SRC)

    def test_two_edits_same_file_compound(self):
        edits = [{"file": "pkg/m.py", "search": "def f(a):\n    x = a + 1", "replace": "def f(a):\n    x = a + 10"},
                 {"file": "pkg/m.py", "search": "def g(b):\n    x = b + 1", "replace": "def g(b):\n    x = b + 20"}]
        apply_edits(self.root, edits)
        text = (self.root / "pkg" / "m.py").read_text()
        self.assertIn("a + 10", text)
        self.assertIn("b + 20", text)

    def test_path_safety(self):
        for bad in ["../outside.py", "/etc/passwd", "pkg/../../x.py", "C:/x.py", "pkg\\m.py", ".git/config", ""]:
            with self.assertRaises(PatchError, msg=bad):
                apply_edits(self.root, self.edit(file=bad))

    def test_cannot_edit_tests_config_or_nonsource(self):
        for f in ["tests/test_m.py", "conftest.py", "data.json"]:
            with self.assertRaises(PatchError, msg=f):
                apply_edits(self.root, self.edit(file=f, search="def test_x(): pass\n"))

    def test_cannot_create_new_files(self):
        with self.assertRaises(PatchError):
            apply_edits(self.root, self.edit(file="pkg/new.py"))
        self.assertFalse((self.root / "pkg" / "new.py").exists())

    def test_real_symlink_is_refused(self):
        """REAL symlink. Skipped where the OS forbids creating them (Windows without Developer
        Mode/admin: WinError 1314)."""
        target = self.root / "pkg" / "m.py"
        link = self.root / "pkg" / "link.py"
        if not make_symlink(link, target):
            self.skipTest("this OS/user is not allowed to create symlinks")
        with self.assertRaises(PatchError):
            apply_edits(self.root, self.edit(file="pkg/link.py"))
        self.assertEqual(target.read_text(), SRC)  # the file behind the link was not modified

    def test_symlink_check_logic_without_real_symlinks(self):
        """Portable check: if a path is reported as a symlink, the edit must be refused even
        though the 'file' is otherwise a normal, editable source file."""
        plain = self.root / "pkg" / "pretend_link.py"
        plain.write_text(SRC)
        real_is_symlink = Path.is_symlink
        with mock.patch.object(Path, "is_symlink",
                               lambda self: self.name == "pretend_link.py" or real_is_symlink(self)):
            with self.assertRaises(PatchError):
                apply_edits(self.root, self.edit(file="pkg/pretend_link.py"))
        self.assertEqual(plain.read_text(), SRC)
        # control: the same edit on the same file IS accepted when it is not a symlink
        apply_edits(self.root, self.edit(file="pkg/pretend_link.py"))
        self.assertIn("a + 2", plain.read_text())

    def test_noop_edit_rejected(self):
        with self.assertRaises(PatchError):
            apply_edits(self.root, self.edit(replace="    x = a + 1\n"))

    def test_crlf_preserved(self):
        p = self.root / "pkg" / "crlf.py"
        p.write_bytes(b"def h():\r\n    return 1\r\n")
        apply_edits(self.root, [{"file": "pkg/crlf.py", "search": "    return 1\n", "replace": "    return 2\n"}])
        self.assertEqual(p.read_bytes(), b"def h():\r\n    return 2\r\n")

    def test_no_edits(self):
        with self.assertRaises(PatchError):
            apply_edits(self.root, [])


if __name__ == "__main__":
    unittest.main()
