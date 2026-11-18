#!/usr/bin/env python3
"""Evaluation script for CodePilotX.

Modes (each measures something different -- read the README before quoting numbers):

  retrieval  (default) No LLM, no Docker. For every task: is the known-buggy function among the
             retrieved evidence? Reports hit@top-k (similarity only) and hit with call-following.
  oracle     Needs Docker. Replays the KNOWN-CORRECT fix + test through the full pipeline with a
             scripted (fake) LLM. Checks that the *validation harness* works: expected result is
             'validated' for every task. This does NOT measure any LLM.
  full       Needs an LLM key (+ Docker for validation). Runs the real model on every task and
             reports how many fixes ended 'validated'.

Usage (from the repository root):
  python evaluation/run_eval.py                 # retrieval
  python evaluation/run_eval.py --mode oracle
  python evaluation/run_eval.py --mode full
Results are also written to evaluation/results/<mode>-<timestamp>.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import SAMPLES_DIR, Settings  # noqa: E402
from app.llm.client import get_llm  # noqa: E402
from app.rag.embeddings import HashingEmbedder, get_embedder  # noqa: E402
from app.rag.retriever import CodeIndex  # noqa: E402
from app.repo.analyzer import chunk_repo  # noqa: E402
from app.repo.loader import copy_local_tree, iter_source_files  # noqa: E402
from app.sandbox import DockerSandbox  # noqa: E402
from app.workflow import Deps, run_pipeline  # noqa: E402


def load_tasks() -> list[dict]:
    return json.loads((SAMPLES_DIR / "tasks.json").read_text(encoding="utf-8"))


def hit(res, task) -> bool:
    return any(r.chunk.path == task["expected_file"] and r.chunk.name == task["expected_symbol"] for r in res)


def eval_retrieval(settings: Settings) -> list[dict]:
    rows = []
    for t in load_tasks():
        with tempfile.TemporaryDirectory() as d:
            root = copy_local_tree(SAMPLES_DIR / t["repo"].split(":")[1], Path(d) / "r", settings)
            files, _ = iter_source_files(root, settings)
            idx = CodeIndex(chunk_repo(files), get_embedder(settings.embedding_backend, settings.embedding_model))
            strict = idx.retrieve(t["issue"], k=settings.top_k, max_callees=0)
            full = idx.retrieve(t["issue"], k=settings.top_k)
            rank = next((i + 1 for i, r in enumerate(full) if r.chunk.path == t["expected_file"]
                         and r.chunk.name == t["expected_symbol"]), None)
        rows.append({"task": t["id"], "difficulty": t["difficulty"], "hit_top_k": hit(strict, t),
                     "hit_with_call_following": hit(full, t), "rank_in_final_set": rank})
    return rows


class _Oracle:
    """Scripted stand-in for an LLM that answers with the reference solution."""
    model = "oracle-replay"

    def __init__(self, task):
        self.replies = [
            json.dumps({"summary": "s", "root_cause": "known", "confidence": "high", "suspects": [
                {"file": task["expected_file"], "symbol": task["expected_symbol"], "reason": "reference"}]}),
            json.dumps({"explanation": "reference fix", "edits": task["reference_edits"],
                        "test_code": task["reference_test"], "test_rationale": "reference"})]

    def complete(self, system, user):
        return self.replies.pop(0)


def eval_pipeline(settings: Settings, oracle: bool) -> list[dict]:
    sandbox = DockerSandbox(settings)
    ok, why = sandbox.availability()
    if not ok:
        print(f"NOTE: sandbox unavailable ({why}). Verdicts will be 'not_validated'.")
    llm_real = get_llm(settings)
    if not oracle and llm_real is None:
        sys.exit("full mode needs an LLM key: set ANTHROPIC_API_KEY (or OPENAI_*) in .env")
    rows = []
    for t in load_tasks():
        llm = _Oracle(t) if oracle else llm_real
        deps = Deps(settings, llm, sandbox, lambda: get_embedder(settings.embedding_backend, settings.embedding_model))
        t0 = time.time()
        res = run_pipeline(deps, t["repo"], t["issue"])
        rows.append({"task": t["id"], "difficulty": t["difficulty"], "status": res["final"]["status"],
                     "verdict": res["final"]["verdict"], "verified_fix": res["final"]["verified_fix"],
                     "attempts": len(res["attempts"]), "seconds": round(time.time() - t0, 1),
                     "message": res["final"]["message"][:160]})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["retrieval", "oracle", "full"], default="retrieval")
    args = ap.parse_args()
    settings = Settings.from_env()
    rows = eval_retrieval(settings) if args.mode == "retrieval" else eval_pipeline(settings, args.mode == "oracle")

    print(f"\nMode: {args.mode}   tasks: {len(rows)}\n")
    for r in rows:
        print("  " + "  ".join(f"{k}={v}" for k, v in r.items() if k != "difficulty"))
    n = len(rows)
    if args.mode == "retrieval":
        print(f"\nhit@top-{settings.top_k} (similarity + hints only): {sum(r['hit_top_k'] for r in rows)}/{n}")
        print(f"hit with call-following:                {sum(r['hit_with_call_following'] for r in rows)}/{n}")
    else:
        print(f"\nvalidated fixes: {sum(r['verified_fix'] for r in rows)}/{n}")
    out = ROOT / "evaluation" / "results"
    out.mkdir(exist_ok=True)
    path = out / f"{args.mode}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(rows, indent=2))
    print(f"saved: {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
