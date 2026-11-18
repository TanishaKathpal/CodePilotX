import unittest

from app.models import RepoFile
from app.repo.analyzer import (chunk_file, chunk_python, detect_test_targets, is_test_path,
                               summarize_repo)


def pyfile(path, text):
    return RepoFile(path=path, language="python", size=len(text), text=text)


SRC = '''"""mod doc"""
import os

LIMIT = 3


@decorator
def helper(a):
    """Help."""
    return a + 1


class Thing:
    """A thing."""
    kind = "x"

    def run(self, n):
        return helper(n)

    async def go(self):
        return 1


if __name__ == "__main__":
    helper(1)
'''


class ChunkingTests(unittest.TestCase):
    def setUp(self):
        self.chunks = chunk_python(pyfile("pkg/mod.py", SRC))
        self.by_name = {c.name: c for c in self.chunks if c.name}

    def test_function_boundaries_include_decorator(self):
        c = self.by_name["helper"]
        self.assertEqual(c.kind, "function")
        self.assertTrue(c.text.startswith("@decorator"))
        self.assertTrue(c.text.rstrip().endswith("return a + 1"))
        self.assertEqual(c.docstring, "Help.")
        self.assertEqual(c.id, f"pkg/mod.py:{c.start_line}-{c.end_line}")

    def test_methods_are_qualified_and_record_calls(self):
        self.assertIn("Thing.run", self.by_name)
        self.assertIn("Thing.go", self.by_name)
        self.assertIn("helper", self.by_name["Thing.run"].calls)

    def test_class_header_chunk(self):
        c = self.by_name["Thing"]
        self.assertEqual(c.kind, "class")
        self.assertIn("kind", c.text)
        self.assertNotIn("def run", c.text)

    def test_module_level_code_is_covered(self):
        mods = [c for c in self.chunks if c.kind == "module"]
        joined = "\n".join(c.text for c in mods)
        self.assertIn("import os", joined)
        self.assertIn("__main__", joined)

    def test_every_line_covered_once_by_symbol_or_module(self):
        lines = SRC.splitlines()
        covered = set()
        for c in self.chunks:
            for ln in range(c.start_line, c.end_line + 1):
                self.assertNotIn(ln, covered, f"line {ln} in two chunks")
                covered.add(ln)
        blank_or_covered = all((i + 1) in covered or not lines[i].strip() for i in range(len(lines)))
        self.assertTrue(blank_or_covered)

    def test_chunk_text_matches_source_lines_exactly(self):
        lines = SRC.splitlines()
        for c in self.chunks:
            self.assertEqual(c.text, "\n".join(lines[c.start_line - 1:c.end_line]))

    def test_syntax_error_falls_back_to_windows(self):
        cs = chunk_python(pyfile("old.py", "print 'hello'\n" * 5))
        self.assertTrue(cs and all(c.kind == "block" for c in cs))

    def test_long_function_is_split(self):
        body = "\n".join(f"    x{i} = {i}" for i in range(300))
        cs = chunk_python(pyfile("big.py", f"def big():\n{body}\n"))
        parts = [c for c in cs if c.name == "big"]
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(c.end_line - c.start_line < 70 for c in parts))

    def test_non_python_uses_windows(self):
        f = RepoFile("a.js", "javascript", 10, "\n".join(f"line{i}" for i in range(150)))
        cs = chunk_file(f)
        self.assertGreaterEqual(len(cs), 3)
        self.assertEqual(cs[0].start_line, 1)

    def test_empty_file(self):
        self.assertEqual(chunk_python(pyfile("e.py", "")), [])


class SummaryTests(unittest.TestCase):
    def test_test_path_detection(self):
        for p in ["tests/test_a.py", "pkg/test_x.py", "pkg/x_test.py", "conftest.py", "test/helpers.py",
                  "pkg/tests/util.py"]:
            self.assertTrue(is_test_path(p), p)
        for p in ["pkg/contest.py", "pkg/latest.py", "src/attestation.py"]:
            self.assertFalse(is_test_path(p), p)

    def test_detect_targets(self):
        files = [pyfile("tests/test_a.py", ""), pyfile("tests/test_b.py", ""), pyfile("pkg/test_c.py", ""),
                 pyfile("pkg/real.py", ""), pyfile("conftest.py", "")]
        self.assertEqual(detect_test_targets(files), ["tests", "pkg/test_c.py"])

    def test_summary_fields_and_notes(self):
        files = [pyfile("pkg/a.py", "def f():\n    pass\n"), pyfile("tests/test_a.py", "def test_f(): pass\n"),
                 RepoFile("requirements.txt", "text", 5, "numpy\npytest\n")]
        chunks = [c for f in files for c in chunk_file(f)]
        s = summarize_repo(files, chunks, ["warn1"])
        self.assertEqual(s["primary_language"], "python")
        self.assertTrue(s["validation_supported"])
        self.assertEqual(s["test_targets"], ["tests"])
        self.assertIn("requirements.txt", s["key_files"])
        self.assertTrue(any("third-party" in n for n in s["notes"]))
        self.assertIn("warn1", s["notes"])
        self.assertEqual(s["symbol_count"], 1)  # tests are not counted as project symbols

    def test_non_python_repo_flagged(self):
        f = RepoFile("a.js", "javascript", 10, "const a = 1;\n")
        s = summarize_repo([f], chunk_file(f))
        self.assertFalse(s["validation_supported"])
        self.assertTrue(any("only supported for Python" in n for n in s["notes"]))


if __name__ == "__main__":
    unittest.main()
