import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.config import SAMPLES_DIR
from app.repo import loader
from app.repo.loader import RepoError
from tests.helpers import make_settings, make_symlink


class UrlValidationTests(unittest.TestCase):
    def test_accepts_normal_github_urls(self):
        for url in ["https://github.com/pallets/click", "https://github.com/pallets/click.git",
                    "https://github.com/pallets/click/", "https://github.com/a-b/c_d.e"]:
            self.assertEqual(len(loader.parse_github_url(url)), 2, url)

    def test_rejects_everything_else(self):
        bad = ["http://github.com/a/b", "file:///etc/passwd", "git@github.com:a/b.git",
               "ssh://github.com/a/b", "https://gitlab.com/a/b", "https://github.com/a",
               "https://github.com/a/b/tree/main", "https://github.com.evil.com/a/b",
               "https://github.com/a/b;rm -rf /", "https://user:pw@github.com/a/b", "/etc", "",
               "https://github.com/a/b/../../c", "--upload-pack=evil"]
        for url in bad:
            with self.assertRaises(RepoError, msg=url):
                loader.parse_github_url(url)

    def test_sample_refs(self):
        self.assertEqual(loader.resolve_repo_ref("sample:bank"), ("sample", "bank"))
        with self.assertRaises(RepoError):
            loader.resolve_repo_ref("sample:../../etc")
        with self.assertRaises(RepoError):
            loader.resolve_repo_ref("sample:doesnotexist")


class SanitizeTests(unittest.TestCase):
    def test_git_dir_removed_and_normal_files_kept(self):
        """Needs no symlinks, so it runs on every platform."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "r"
            (root / ".git").mkdir(parents=True)
            (root / ".git" / "config").write_text("x")
            (root / "a.py").write_text("x = 1\n")
            loader.sanitize_tree(root, make_settings(d))
            self.assertFalse((root / ".git").exists())
            self.assertTrue((root / "a.py").exists())

    def test_real_symlinks_are_removed(self):
        """Uses REAL symlinks. Skipped (not failed) where the OS forbids creating them, e.g.
        Windows without Developer Mode / admin rights (WinError 1314)."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "r"
            root.mkdir()
            (root / "a.py").write_text("x = 1\n")
            outside = Path(d) / "outside_secret.txt"
            outside.write_text("secret")
            file_link, dir_link = root / "evil_link", root / "evil_dir"
            if not make_symlink(file_link, outside):
                self.skipTest("this OS/user is not allowed to create symlinks")
            self.assertTrue(make_symlink(dir_link, Path(d), target_is_directory=True))
            loader.sanitize_tree(root, make_settings(d))
            self.assertFalse(file_link.is_symlink() or file_link.exists())
            self.assertFalse(dir_link.is_symlink() or dir_link.exists())
            self.assertTrue((root / "a.py").exists())
            self.assertEqual(outside.read_text(), "secret")  # the link target itself was NOT touched

    def test_symlink_removal_logic_without_real_symlinks(self):
        """Portable check of the deletion branch: we make sanitize_tree *believe* that a plain
        file is a symlink. This proves the code unlinks whatever is_symlink() reports, on any OS.
        (It does not prove is_symlink() itself works - the real-symlink test above does that.)"""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "r"
            root.mkdir()
            (root / "keep.py").write_text("x = 1\n")
            (root / "evil_link").write_text("pretend I am a symlink")
            real_is_symlink = Path.is_symlink
            with mock.patch.object(Path, "is_symlink",
                                   lambda self: self.name == "evil_link" or real_is_symlink(self)):
                loader.sanitize_tree(root, make_settings(d))
            self.assertFalse((root / "evil_link").exists())
            self.assertTrue((root / "keep.py").exists())

    def test_size_limit(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "r"
            root.mkdir()
            (root / "big.bin").write_bytes(b"\0" * (2 * 1024 * 1024))
            with self.assertRaises(RepoError) as cm:
                loader.sanitize_tree(root, make_settings(d, max_repo_mb=1))
            self.assertIn("MAX_REPO_MB", str(cm.exception))


class IterFilesTests(unittest.TestCase):
    def test_skips_junk_binary_and_big(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "node_modules" / "x").mkdir(parents=True)
            (root / "node_modules" / "x" / "i.js").write_text("1")
            (root / "good.py").write_text("print(1)\n")
            (root / "bin.py").write_bytes(b"abc\x00def")
            (root / "huge.py").write_text("x=1\n" * 100000)
            (root / "notes.xyz").write_text("unknown ext")
            files, warns = loader.iter_source_files(root, make_settings(d, max_file_kb=50))
            self.assertEqual([f.path for f in files], ["good.py"])
            self.assertTrue(any("larger than" in w for w in warns))

    def test_file_cap(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(10):
                (Path(d) / f"f{i}.py").write_text("x=1\n")
            files, warns = loader.iter_source_files(Path(d), make_settings(d, max_files_indexed=3))
            self.assertEqual(len(files), 3)
            self.assertTrue(any("MAX_FILES_INDEXED" in w for w in warns))


class CloneTests(unittest.TestCase):
    def test_git_command_is_hardened(self):
        captured = {}

        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            return mock.Mock(returncode=1, stderr="fatal: nope", stdout="")
        with tempfile.TemporaryDirectory() as d, mock.patch("subprocess.run", fake_run):
            with self.assertRaises(RepoError):
                loader.clone_github("https://github.com/a/b", Path(d) / "x", make_settings(d))
        cmd = captured["cmd"]
        for needle in ["core.hooksPath=/dev/null", "core.symlinks=false", "protocol.file.allow=never",
                       "--depth", "--"]:
            self.assertTrue(any(needle in c for c in cmd), needle)
        self.assertLess(cmd.index("--"), cmd.index("https://github.com/a/b"))

    def test_real_git_refuses_local_paths(self):
        """Proves the protocol.file.allow=never flag works with the real git binary."""
        import shutil
        import subprocess
        if shutil.which("git") is None:
            self.skipTest("git not installed")
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "src"
            src.mkdir()
            env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                   "GIT_COMMITTER_EMAIL": "t@t"}
            subprocess.run(["git", "init", "-q", str(src)], check=True, env=env)
            (src / "a.py").write_text("x=1\n")
            subprocess.run(["git", "-C", str(src), "add", "."], check=True, env=env)
            subprocess.run(["git", "-C", str(src), "commit", "-qm", "i"], check=True, env=env)
            with self.assertRaises(RepoError):
                loader._run_git_clone(f"file://{src}", Path(d) / "dst", make_settings(d))
            self.assertFalse((Path(d) / "dst").exists())


class SampleLoadTests(unittest.TestCase):
    def test_load_sample(self):
        with tempfile.TemporaryDirectory() as d:
            root = loader.load_repo("sample:bank", Path(d) / "r", make_settings(d))
            self.assertTrue((root / "bank" / "account.py").is_file())
            self.assertFalse((root / ".git").exists())


if __name__ == "__main__":
    unittest.main()
