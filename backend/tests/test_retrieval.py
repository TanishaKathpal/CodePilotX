import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from app.config import SAMPLES_DIR
from app.rag.embeddings import HashingEmbedder, get_embedder, split_identifier, stem, tokenize
from app.rag.retriever import CodeIndex, extract_hints, rank_files
from app.rag.vector_store import VectorStore
from app.repo.analyzer import chunk_repo
from app.repo.loader import copy_local_tree, iter_source_files
from tests.helpers import make_settings


class EmbeddingTests(unittest.TestCase):
    def test_identifier_splitting(self):
        self.assertEqual(split_identifier("calculateTotal_v2"), ["calculate", "total", "v", "2"])
        self.assertEqual(split_identifier("HTTPServerError"), ["http", "server", "error"])

    def test_tokenize_keeps_whole_identifier_and_parts(self):
        t = tokenize("def count_words(self, text): return text")
        self.assertIn("count_words", t)
        self.assertIn("count", t)
        self.assertIn("word", t)       # stemmed from 'words'
        self.assertNotIn("self", t)

    def test_stem(self):
        self.assertEqual(stem("counter"), "count")
        self.assertEqual(stem("counting"), "count")
        self.assertEqual(stem("days"), "days")  # <=4 chars untouched
        self.assertEqual(stem("2000"), "2000")

    def test_embeddings_are_normalised_deterministic_and_similar_texts_closer(self):
        e1, e2 = HashingEmbedder(), HashingEmbedder()
        docs = ["def add_item(cart, sku): cart.append(sku)", "def paginate(items, page): return items",
                "class Account: balance withdraw deposit"]
        e1.fit(docs)
        e2.fit(docs)
        a, b = e1.embed(docs), e2.embed(docs)
        np.testing.assert_allclose(a, b)  # stable across instances/processes
        np.testing.assert_allclose(np.linalg.norm(a, axis=1), 1.0, rtol=1e-5)
        q = e1.embed(["withdraw money from the account balance"])[0]
        self.assertEqual(int(np.argmax(a @ q)), 2)

    def test_empty_text_gives_zero_vector_not_nan(self):
        e = HashingEmbedder()
        e.fit(["x"])
        v = e.embed([""])
        self.assertFalse(np.isnan(v).any())

    def test_factory(self):
        self.assertIsInstance(get_embedder("hashing", ""), HashingEmbedder)
        with self.assertRaises(ValueError):
            get_embedder("nope", "")


class VectorStoreTests(unittest.TestCase):
    def test_search_order_and_k(self):
        vs = VectorStore()
        vs.add(np.array([[1, 0], [0, 1], [0.7, 0.7]], dtype=np.float32), ["x", "y", "xy"])
        res = vs.search(np.array([1, 0], dtype=np.float32), 2)
        self.assertEqual([r[0] for r in res], ["x", "xy"])
        self.assertEqual(len(vs.search(np.array([1, 0], dtype=np.float32), 99)), 3)

    def test_empty_and_mismatch(self):
        vs = VectorStore()
        self.assertEqual(vs.search(np.zeros(2, dtype=np.float32), 3), [])
        vs.add(np.ones((1, 2), dtype=np.float32), ["a"])
        with self.assertRaises(ValueError):
            vs.add(np.ones((1, 3), dtype=np.float32), ["b"])
        with self.assertRaises(ValueError):
            vs.add(np.ones((2, 2), dtype=np.float32), ["only one"])


class HintTests(unittest.TestCase):
    def test_traceback(self):
        h = extract_hints('Traceback:\n  File "/app/pkg/mod.py", line 42, in run\n    boom()\nValueError')
        self.assertIn(("/app/pkg/mod.py", 42), h.lines)

    def test_path_with_line_and_backticks(self):
        h = extract_hints("Crash in src/util/dates.py:17 when calling `Cart.total()` and parse_date(x)")
        self.assertIn(("src/util/dates.py", 17), h.lines)
        self.assertIn("Cart.total", h.identifiers)
        self.assertIn("parse_date", h.identifiers)

    def test_dot_prefix_handling(self):
        h = extract_hints("see ./pkg/a.py:3 and .github/scripts/x.py")
        self.assertIn(("pkg/a.py", 3), h.lines)
        self.assertIn(".github/scripts/x.py", h.files)

    def test_builtins_and_filenames_are_not_identifiers(self):
        h = extract_hints("print(len(x)) in foo.py")
        self.assertEqual(h.identifiers, [])


class IndexTests(unittest.TestCase):
    def _index(self, sample):
        d = tempfile.mkdtemp()
        s = make_settings(d)
        root = copy_local_tree(SAMPLES_DIR / sample, Path(d) / "r", s)
        files, _ = iter_source_files(root, s)
        return CodeIndex(chunk_repo(files), HashingEmbedder())

    def test_named_function_ranks_first(self):
        idx = self._index("pagination")
        res = idx.retrieve("paginate(range(10), page=1, per_page=3) returns the wrong items", k=5)
        self.assertEqual(res[0].chunk.name, "paginate")
        self.assertTrue(any("defines `paginate`" in r for r in res[0].reasons))

    def test_traceback_line_boost(self):
        idx = self._index("bank")
        issue = 'File "bank/account.py", line 17, in withdraw\n    raise InsufficientFunds'
        res = idx.retrieve(issue, k=3)
        self.assertEqual(res[0].chunk.path, "bank/account.py")
        self.assertTrue(any("stack-trace line" in r for r in res[0].reasons))

    def test_callee_following(self):
        idx = self._index("shopping_cart")
        strict = idx.retrieve("SAVE10 coupon gives a negative total", k=3, max_callees=0)
        full = idx.retrieve("SAVE10 coupon gives a negative total", k=3)
        names = [r.chunk.name for r in full]
        self.assertGreaterEqual(len(full), len(strict))
        self.assertTrue(any("called by" in " ".join(r.reasons) for r in full), names)

    def test_tests_and_docs_downweighted(self):
        idx = self._index("bank")
        res = idx.retrieve("withdraw balance insufficient funds", k=10)
        for r in res:
            if r.chunk.path.startswith("tests/"):
                self.assertTrue(any("down-weighted" in x for x in r.reasons))

    def test_empty_index(self):
        idx = CodeIndex([], HashingEmbedder())
        self.assertEqual(idx.retrieve("anything"), [])

    def test_rank_files(self):
        idx = self._index("bank")
        rows = rank_files(idx.retrieve("withdraw raises InsufficientFunds", k=6))
        self.assertEqual(rows[0]["path"], "bank/account.py")

    def test_all_sample_tasks_retrieve_expected_symbol(self):
        """Regression guard for retrieval quality on the bundled tasks (with call-following)."""
        tasks = json.loads((SAMPLES_DIR / "tasks.json").read_text())
        misses = []
        for t in tasks:
            idx = self._index(t["repo"].split(":")[1])
            res = idx.retrieve(t["issue"], k=8)
            if not any(r.chunk.path == t["expected_file"] and r.chunk.name == t["expected_symbol"] for r in res):
                misses.append(t["id"])
        self.assertEqual(misses, [])


if __name__ == "__main__":
    unittest.main()
