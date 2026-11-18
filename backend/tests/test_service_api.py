import json
import shutil
import tempfile
import unittest
from pathlib import Path

from app.config import SAMPLES_DIR
from app.rag.embeddings import HashingEmbedder
from app.service import InputError, JobManager
from app.workflow import STEPS, Deps
from tests.helpers import ScriptedLLM, TrustedLocalRunner, make_settings
from tests.test_workflow import TASKS, diag, fix


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cpx-svc-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def manager(self, replies):
        s = make_settings(self.tmp)
        llm = ScriptedLLM(replies) if replies is not None else None
        f = lambda progress: Deps(s, llm, TrustedLocalRunner(), HashingEmbedder, progress)
        return JobManager(s, sandbox=TrustedLocalRunner(), deps_factory=f)

    def test_full_job_lifecycle_and_progress(self):
        t = TASKS["bank-withdraw-full-balance"]
        m = self.manager([diag(t), fix(t)])
        jid = m.submit(t["repo"], t["issue"])
        job = m.wait(jid)
        self.assertEqual(job["status"], "done")
        self.assertEqual(job["result"]["final"]["verdict"], "validated")
        self.assertEqual([s["name"] for s in job["steps"]], [n for n, _ in STEPS])
        self.assertTrue(all(s["status"] == "done" for s in job["steps"]), job["steps"])
        json.dumps(job)

    def test_unused_steps_marked_skipped(self):
        t = TASKS["bank-withdraw-full-balance"]
        m = self.manager(None)
        job = m.wait(m.submit(t["repo"], t["issue"]))
        st = {s["name"]: s["status"] for s in job["steps"]}
        self.assertEqual(st["retrieve"], "done")
        self.assertEqual(st["diagnose"], "skipped")
        self.assertEqual(st["validate"], "skipped")

    def test_input_validation(self):
        m = self.manager([])
        for repo, issue in [("https://evil.com/a/b", "a long enough issue text"), ("sample:bank", "short"),
                            ("sample:bank", "x" * 5000), ("", "a long enough issue text")]:
            with self.assertRaises(InputError):
                m.submit(repo, issue)

    def test_crash_is_contained_and_not_leaked(self):
        s = make_settings(self.tmp)

        def boom(progress):
            raise RuntimeError("secret internal path /root/x")
        m = JobManager(s, sandbox=TrustedLocalRunner(), deps_factory=boom)
        job = m.wait(m.submit("sample:bank", "withdraw fails for full balance"))
        self.assertEqual(job["status"], "failed")
        self.assertNotIn("secret", job["error"])

    def test_unknown_job_and_samples_and_health(self):
        m = self.manager([])
        self.assertIsNone(m.get("nope"))
        self.assertEqual(len(m.samples()), 5)
        h = m.health()
        self.assertTrue(h["sandbox"]["available"])
        self.assertIn(h["orchestrator"], {"langgraph", "sequential"})


try:
    import fastapi, httpx  # noqa: F401
    HAVE_API = True
except ImportError:
    HAVE_API = False


@unittest.skipUnless(HAVE_API, "fastapi/httpx not installed in this environment - run after `pip install -r requirements-dev.txt`")
class ApiTests(unittest.TestCase):
    def test_endpoints(self):
        from fastapi.testclient import TestClient
        from app import main
        c = TestClient(main.app)
        self.assertEqual(c.get("/api/health").status_code, 200)
        self.assertEqual(len(c.get("/api/samples").json()), 5)
        self.assertEqual(c.post("/api/jobs", json={"repo_url": "https://evil.com/a/b", "issue": "long enough issue"}).status_code, 400)
        self.assertEqual(c.get("/api/jobs/nope").status_code, 404)
        r = c.post("/api/jobs", json={"repo_url": "sample:bank", "issue": "withdraw of full balance raises"})
        self.assertEqual(r.status_code, 202)


if __name__ == "__main__":
    unittest.main()
