"""Background jobs: run the pipeline in a thread pool and expose progress to the API.

Kept free of any web-framework imports so it can be tested without FastAPI.
In-memory only: jobs disappear when the server restarts (fine for a single-user tool).
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from .config import SAMPLES_DIR, Settings
from .llm.client import get_llm
from .rag.embeddings import get_embedder
from .repo.loader import RepoError, resolve_repo_ref
from .sandbox import DockerSandbox, Sandbox
from .workflow import STEPS, Deps, langgraph_available, run_pipeline

log = logging.getLogger("codepilotx")
MIN_ISSUE, MAX_ISSUE, MAX_JOBS_KEPT = 10, 4000, 50


class InputError(ValueError):
    """Invalid user input (shown to the user as HTTP 400)."""


class JobManager:
    def __init__(self, settings: Settings, sandbox: Sandbox | None = None,
                 deps_factory: Callable[[Callable], Deps] | None = None):
        self.settings = settings
        self.sandbox = sandbox or DockerSandbox(settings)
        self._deps_factory = deps_factory or self._default_deps
        self._pool = ThreadPoolExecutor(max_workers=settings.max_concurrent_jobs)
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _default_deps(self, progress) -> Deps:
        s = self.settings
        return Deps(settings=s, llm=get_llm(s), sandbox=self.sandbox,
                    make_embedder=lambda: get_embedder(s.embedding_backend, s.embedding_model),
                    progress=progress)

    # ------------------------------------------------------------------ public API
    def health(self) -> dict:
        ok, why = self.sandbox.availability()
        s = self.settings
        return {
            "status": "ok",
            "llm": {"configured": bool(s.llm_api_key) or (s.llm_provider == "openai_compatible"
                    and s.openai_base_url != "https://api.openai.com/v1"),
                    "provider": s.llm_provider, "model": s.llm_model},
            "sandbox": {"available": ok, "detail": why, "image": s.sandbox_image},
            "embedding_backend": s.embedding_backend,
            "orchestrator": "langgraph" if (s.use_langgraph and langgraph_available()) else "sequential",
        }

    def samples(self) -> list[dict]:
        import json
        path = SAMPLES_DIR / "tasks.json"
        if not path.is_file():
            return []
        return [{"id": t["id"], "repo": t["repo"], "issue": t["issue"], "difficulty": t.get("difficulty", "")}
                for t in json.loads(path.read_text(encoding="utf-8"))]

    def submit(self, repo: str, issue: str) -> str:
        repo, issue = (repo or "").strip(), (issue or "").strip()
        try:
            resolve_repo_ref(repo)
        except RepoError as e:
            raise InputError(str(e))
        if not MIN_ISSUE <= len(issue) <= MAX_ISSUE:
            raise InputError(f"The issue description must be between {MIN_ISSUE} and {MAX_ISSUE} characters.")
        job_id = uuid.uuid4().hex[:12]
        job = {"id": job_id, "status": "queued", "repo": repo, "issue": issue, "created": time.time(),
               "steps": [{"name": n, "label": l, "status": "pending", "detail": ""} for n, l in STEPS],
               "result": None, "error": None}
        with self._lock:
            self._jobs[job_id] = job
            for old in sorted(self._jobs, key=lambda k: self._jobs[k]["created"])[:-MAX_JOBS_KEPT]:
                del self._jobs[old]
        self._pool.submit(self._run, job_id)
        return job_id

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return {**job, "steps": [dict(s) for s in job["steps"]]}

    def wait(self, job_id: str, timeout: float = 60) -> dict:
        """Test helper: block until a job finishes."""
        end = time.time() + timeout
        while time.time() < end:
            j = self.get(job_id)
            if j and j["status"] in {"done", "failed"}:
                return j
            time.sleep(0.05)
        raise TimeoutError(job_id)

    # ------------------------------------------------------------------ internals
    def _progress(self, job_id: str):
        def cb(step: str, status: str, detail: str = "") -> None:
            with self._lock:
                job = self._jobs.get(job_id)
                if not job:
                    return
                for s in job["steps"]:
                    if s["name"] == step:
                        s["status"], s["detail"] = status, detail
        return cb

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job["status"] = "running"
            repo, issue = job["repo"], job["issue"]
        try:
            deps = self._deps_factory(self._progress(job_id))
            result = run_pipeline(deps, repo, issue, job_id)
            with self._lock:
                job["result"], job["status"] = result, "done"
        except Exception:  # never leak internals to users; details go to the server log
            log.exception("job %s crashed", job_id)
            with self._lock:
                job["status"] = "failed"
                job["error"] = "An internal error occurred while processing this job. See the server log."
        finally:
            with self._lock:
                for s in job["steps"]:
                    if s["status"] in {"pending", "running"}:
                        s["status"] = "skipped" if job["status"] == "done" else "failed" if s["status"] == "running" else "skipped"
