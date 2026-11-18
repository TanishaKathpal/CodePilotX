"""The agent workflow.

    load_repo -> analyze_repo -> index_repo -> retrieve -> diagnose -> propose_fix
                                                                          ^   |
                                                                          |   v
                                                            (retry w/ feedback) apply_patch -> validate -> finalize

Each node is a plain function `node(state) -> dict_of_updates` -- exactly the shape LangGraph
expects. That means:
  * with `langgraph` installed we wire the nodes into a LangGraph StateGraph (conditional edges
    implement the retry loop), and
  * without it we run the very same nodes and routing rules in a simple loop.
All the logic lives in the nodes and routers, so both runners behave identically.

Honesty rule: the final verdict is "validated" ONLY when sandboxed tests actually ran and
passed (see validation.py). In every other situation the UI shows a modest, specific status.
"""
from __future__ import annotations

import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypedDict

from .config import Settings
from .llm.client import LLM, LLMError, LLMFormatError, extract_json
from .llm.prompts import SYSTEM_PROMPT, diagnose_prompt, fix_prompt, format_context
from .llm.schemas import parse_diagnosis, parse_fix
from .models import RetrievedChunk, TestRunResult
from .patching import PatchError, apply_edits
from .rag.embeddings import Embedder
from .rag.retriever import CodeIndex, extract_hints, rank_files
from .repo.analyzer import chunk_repo, summarize_repo
from .repo.loader import RepoError, iter_source_files, load_repo
from .sandbox import Sandbox
from .validation import GENERATED_DIR, GENERATED_FILE, VERDICT_LABELS, Verdict, judge

STEPS = [
    ("load_repo", "Fetch repository"),
    ("analyze_repo", "Analyze structure"),
    ("index_repo", "Build vector index"),
    ("retrieve", "Retrieve relevant code"),
    ("diagnose", "Diagnose with LLM"),
    ("propose_fix", "Propose fix & tests"),
    ("apply_patch", "Apply patch"),
    ("validate", "Validate in sandbox"),
]
RETRYABLE = {"not_reproduced", "fix_failed", "regression", "test_error"}
MAX_FILE_CHARS_IN_PROMPT = 12000
EVIDENCE_CODE_CHARS = 3000


class PipelineState(TypedDict, total=False):
    repo_ref: str
    issue: str
    workdir: Any
    repo_root: Any
    files: Any
    file_map: Any
    chunks: Any
    summary: dict
    warnings: list
    index: Any
    hints: Any
    retrieved: list
    included_ids: list
    diagnosis: dict
    attempts: list
    attempt_no: int
    feedback: str
    abort: str
    diag_error: str
    fix_error: str
    result: dict
    timings: dict


@dataclass
class Deps:
    settings: Settings
    llm: LLM | None
    sandbox: Sandbox
    make_embedder: Callable[[], Embedder]
    progress: Callable[[str, str, str], None] = lambda step, status, detail="": None


# ---------------------------------------------------------------------------- helpers

def _ask_json(llm: LLM, system: str, user: str, parse: Callable[[dict], dict]) -> dict:
    """Call the model; if the reply is not valid/complete JSON, ask once more with the error."""
    prompt = user
    for attempt in range(2):
        text = llm.complete(system, prompt)
        try:
            return parse(extract_json(text))
        except LLMFormatError as e:
            if attempt == 1:
                raise
            prompt = (user + f"\n\nYour previous reply was rejected: {e} "
                             "Reply again with ONE valid JSON object that follows the schema exactly.")
    raise LLMError("unreachable")  # pragma: no cover


def _timed(state: PipelineState, name: str, t0: float) -> dict:
    """Return the NEW timings dict. Nodes must put it in their returned update: mutating the
    shared state in place is not guaranteed to be kept by every runner (e.g. LangGraph)."""
    return {**state.get("timings", {}), name: round(time.time() - t0, 2)}


def _write_generated_test(root: Path, code: str) -> None:
    d = root / GENERATED_DIR
    d.mkdir(exist_ok=True)
    (d / "test_codepilotx_generated.py").write_text(code, encoding="utf-8")


def _outcomes_view(res: TestRunResult, limit: int = 60) -> dict:
    return {
        "ran": res.ran, "error": res.error, "exit_code": res.exit_code,
        "duration_s": round(res.duration_s, 2),
        "passed": res.count("passed"), "failed": res.count("failed"),
        "errors": res.count("error"), "skipped": res.count("skipped"),
        "tests": [{"id": o.id, "status": o.status, "message": o.message[:200]} for o in res.outcomes[:limit]],
        "output_tail": res.output_tail[-2500:],
    }


def _feedback_for(verdict: Verdict, before: TestRunResult, after: TestRunResult) -> str:
    tail = (after.output_tail if verdict.verdict in {"fix_failed", "regression"} else before.output_tail)[-1800:]
    hint = {
        "not_reproduced": "Your test passed on the ORIGINAL code, so it does not capture the bug. "
                          "Write a test whose assertion fails because of the bug.",
        "fix_failed": "After your edit the test still failed. Re-read the code and the failure output.",
        "regression": "Your edit broke tests that used to pass: " + ", ".join(verdict.regressions[:5]),
        "test_error": "The generated test could not run (syntax/import problem). Fix the test file.",
    }.get(verdict.verdict, verdict.message)
    return f"{verdict.message}\n{hint}\nTest output (tail):\n{tail}"


# ---------------------------------------------------------------------------- nodes

def make_nodes(deps: Deps) -> dict[str, Callable[[PipelineState], dict]]:
    s = deps.settings

    def load_repo_node(state: PipelineState) -> dict:
        deps.progress("load_repo", "running", "")
        t0 = time.time()
        try:
            root = load_repo(state["repo_ref"], Path(state["workdir"]) / "repo", s)
        except RepoError as e:
            deps.progress("load_repo", "failed", str(e))
            return {"abort": str(e)}
        timings = _timed(state, "load_repo", t0)
        deps.progress("load_repo", "done", "")
        return {"repo_root": root, "timings": timings}

    def analyze_node(state: PipelineState) -> dict:
        deps.progress("analyze_repo", "running", "")
        t0 = time.time()
        files, warnings = iter_source_files(state["repo_root"], s)
        if not files:
            msg = "No supported source files were found in this repository."
            deps.progress("analyze_repo", "failed", msg)
            return {"abort": msg}
        chunks = chunk_repo(files)
        summary = summarize_repo(files, chunks, warnings)
        timings = _timed(state, "analyze_repo", t0)
        deps.progress("analyze_repo", "done",
                      f"{summary['file_count']} files, {summary['symbol_count']} symbols")
        return {"files": files, "file_map": {f.path: f for f in files}, "chunks": chunks,
                "summary": summary, "warnings": warnings, "timings": timings}

    def index_node(state: PipelineState) -> dict:
        deps.progress("index_repo", "running", "")
        t0 = time.time()
        index = CodeIndex(state["chunks"], deps.make_embedder())
        timings = _timed(state, "index_repo", t0)
        deps.progress("index_repo", "done", f"{len(state['chunks'])} chunks, {index.embedder.name}")
        return {"index": index, "timings": timings}

    def retrieve_node(state: PipelineState) -> dict:
        deps.progress("retrieve", "running", "")
        t0 = time.time()
        hints = extract_hints(state["issue"])
        retrieved = state["index"].retrieve(state["issue"], k=s.top_k, hints=hints)
        _, included = format_context(retrieved, s.max_context_chars)
        timings = _timed(state, "retrieve", t0)
        deps.progress("retrieve", "done", f"{len(retrieved)} code snippets")
        return {"hints": hints, "retrieved": retrieved, "included_ids": included, "timings": timings}

    def diagnose_node(state: PipelineState) -> dict:
        deps.progress("diagnose", "running", deps.llm.model if deps.llm else "")
        t0 = time.time()
        prompt, _ = diagnose_prompt(state["issue"], state["summary"], state["retrieved"], s.max_context_chars)
        known = set(state["file_map"])
        try:
            diag = _ask_json(deps.llm, SYSTEM_PROMPT, prompt, lambda o: parse_diagnosis(o, known))
        except LLMError as e:
            deps.progress("diagnose", "failed", str(e))
            return {"diag_error": str(e)}
        timings = _timed(state, "diagnose", t0)
        deps.progress("diagnose", "done", f"confidence: {diag['confidence']}")
        return {"diagnosis": diag, "timings": timings}

    def _file_sources(state: PipelineState) -> dict[str, str]:
        """Verbatim source the model may edit: whole suspect files (if small) else retrieved chunks."""
        suspects = [x["file"] for x in state["diagnosis"]["suspects"] if x["verified"]]
        if not suspects:
            suspects = [r.chunk.path for r in state["retrieved"][:2]]
        out: dict[str, str] = {}
        for path in dict.fromkeys(suspects):
            if len(out) >= 3:
                break
            f = state["file_map"].get(path)
            if f is None:
                continue
            if len(f.text) <= MAX_FILE_CHARS_IN_PROMPT:
                out[path] = f.text
            else:
                parts = [r.chunk.text for r in state["retrieved"] if r.chunk.path == path]
                out[path] = "\n\n# ... (file truncated; showing retrieved sections) ...\n\n".join(parts)
        return out

    def fix_node(state: PipelineState) -> dict:
        n = state.get("attempt_no", 0) + 1
        deps.progress("propose_fix", "running", f"attempt {n} of {s.max_fix_attempts}")
        t0 = time.time()
        sources = _file_sources(state)
        prompt = fix_prompt(state["issue"], state["diagnosis"], sources, state.get("feedback"),
                            state["summary"]["validation_supported"])
        try:
            fix = _ask_json(deps.llm, SYSTEM_PROMPT, prompt, parse_fix)
        except LLMError as e:
            deps.progress("propose_fix", "failed", str(e))
            return {"fix_error": str(e), "attempt_no": n}
        timings = _timed(state, f"propose_fix_{n}", t0)
        deps.progress("propose_fix", "done", f"attempt {n}: {len(fix['edits'])} edit(s)")
        attempts = list(state.get("attempts", []))
        attempts.append({"n": n, **fix, "diff": "", "apply_error": "", "validation": None})
        return {"attempts": attempts, "attempt_no": n, "feedback": "", "timings": timings}

    def patch_node(state: PipelineState) -> dict:
        deps.progress("apply_patch", "running", "")
        attempts = list(state["attempts"])
        cur = attempts[-1]
        patched = Path(state["workdir"]) / f"patched_{cur['n']}"
        shutil.copytree(state["repo_root"], patched)
        try:
            res = apply_edits(patched, cur["edits"])
        except PatchError as e:
            cur["apply_error"] = str(e)
            deps.progress("apply_patch", "failed", str(e))
            return {"attempts": attempts, "feedback": f"Your edit could not be applied: {e}"}
        cur["diff"] = res.diff
        deps.progress("apply_patch", "done", f"{len(res.files)} file(s) changed")
        return {"attempts": attempts}

    def validate_node(state: PipelineState) -> dict:
        deps.progress("validate", "running", "")
        attempts = list(state["attempts"])
        cur = attempts[-1]
        timings = state.get("timings", {})

        def finish(verdict: Verdict, before=None, after=None, fb: str = "") -> dict:
            cur["validation"] = {
                "verdict": verdict.verdict, "message": verdict.message, "reproduced": verdict.reproduced,
                "regressions": verdict.regressions,
                "before": _outcomes_view(before) if before else None,
                "after": _outcomes_view(after) if after else None,
            }
            deps.progress("validate", "done" if verdict.verdict == "validated" else "failed", verdict.verdict)
            return {"attempts": attempts, "feedback": fb, "timings": timings}

        if not state["summary"]["validation_supported"]:
            return finish(Verdict("not_validated", "Automated test execution is only supported for Python "
                                                   "repositories; review the suggested fix manually."))
        ok, why = deps.sandbox.availability()
        if not ok:
            return finish(Verdict("not_validated", f"Sandbox unavailable: {why}"))

        wd = Path(state["workdir"])
        before_root, after_root = wd / f"before_{cur['n']}", wd / f"patched_{cur['n']}"
        shutil.copytree(state["repo_root"], before_root)
        _write_generated_test(before_root, cur["test_code"])
        _write_generated_test(after_root, cur["test_code"])
        targets = list(state["summary"]["test_targets"]) + [GENERATED_FILE]
        t0 = time.time()
        before = deps.sandbox.run_tests(before_root, targets)
        after = deps.sandbox.run_tests(after_root, targets) if before.ran else TestRunResult(ran=False, error="skipped")
        timings = _timed(state, f"validate_{cur['n']}", t0)
        verdict = judge(before, after)
        fb = _feedback_for(verdict, before, after) if verdict.verdict in RETRYABLE else ""
        return finish(verdict, before, after, fb)

    def finalize_node(state: PipelineState) -> dict:
        retrieved: list[RetrievedChunk] = state.get("retrieved", [])
        included = set(state.get("included_ids", []))
        evidence = []
        for i, r in enumerate(retrieved, start=1):
            c = r.chunk
            evidence.append({
                "id": f"C{i}", "path": c.path, "start_line": c.start_line, "end_line": c.end_line,
                "kind": c.kind, "name": c.name, "language": c.language, "score": round(r.score, 3),
                "reasons": r.reasons, "code": c.text[:EVIDENCE_CODE_CHARS],
                "truncated": len(c.text) > EVIDENCE_CODE_CHARS, "sent_to_llm": f"C{i}" in included,
            })
        attempts = state.get("attempts", [])
        last = attempts[-1] if attempts else None
        notes: list[str] = []
        if state.get("abort"):
            final = {"status": "failed", "verdict": None, "verified_fix": False, "message": state["abort"]}
        elif deps.llm is None:
            final = {"status": "retrieval_only", "verdict": None, "verified_fix": False,
                     "message": "No LLM API key is configured, so only the repository analysis and the "
                                "retrieved evidence are shown. Set the key in .env to get a diagnosis and fix."}
        elif state.get("diag_error"):
            final = {"status": "partial", "verdict": None, "verified_fix": False,
                     "message": f"The LLM diagnosis failed: {state['diag_error']}"}
        elif state.get("fix_error") and not last:
            final = {"status": "partial", "verdict": None, "verified_fix": False,
                     "message": f"A diagnosis was produced but no fix could be generated: {state['fix_error']}"}
        else:
            if state.get("fix_error"):
                notes.append(f"A later attempt failed to produce a fix: {state['fix_error']}")
            if last and last["apply_error"]:
                verdict, msg = "patch_failed", f"{VERDICT_LABELS['patch_failed']}: {last['apply_error']}"
            elif last and last["validation"]:
                verdict, msg = last["validation"]["verdict"], last["validation"]["message"]
            else:  # pragma: no cover - defensive
                verdict, msg = "not_validated", VERDICT_LABELS["not_validated"]
            final = {"status": "completed", "verdict": verdict, "verified_fix": verdict == "validated",
                     "message": msg, "label": VERDICT_LABELS.get(verdict, verdict)}
        if final["verdict"] != "validated" and last:
            notes.append("The suggested change is a PROPOSAL. It has not been shown to fix the issue; "
                         "review it and run your own tests before using it.")
        result = {
            "repo": state.get("summary"),
            "warnings": state.get("warnings", []),
            "hints": state["hints"].as_dict() if state.get("hints") else None,
            "relevant_files": rank_files(retrieved) if retrieved else [],
            "evidence": evidence,
            "diagnosis": state.get("diagnosis"),
            "attempts": attempts,
            "final": final,
            "notes": notes,
            "llm": {"configured": deps.llm is not None, "model": deps.llm.model if deps.llm else None},
            "embedding": state["index"].embedder.name if state.get("index") else None,
            "timings": state.get("timings", {}),
        }
        return {"result": result}

    return {
        "load_repo": load_repo_node, "analyze_repo": analyze_node, "index_repo": index_node,
        "retrieve": retrieve_node, "diagnose": diagnose_node, "propose_fix": fix_node,
        "apply_patch": patch_node, "validate": validate_node, "finalize": finalize_node,
    }


# ---------------------------------------------------------------------------- routing

def make_routes(deps: Deps) -> dict[str, tuple[Callable[[PipelineState], str], list[str]]]:
    """name -> (router, possible_targets). Routers decide the next node from the state."""
    max_attempts = deps.settings.max_fix_attempts

    def stop_if_abort(nxt: str) -> Callable[[PipelineState], str]:
        return lambda st: "finalize" if st.get("abort") else nxt

    def after_retrieve(st):
        return "finalize" if deps.llm is None else "diagnose"

    def after_diagnose(st):
        return "finalize" if st.get("diag_error") else "propose_fix"

    def after_fix(st):
        return "finalize" if st.get("fix_error") else "apply_patch"

    def after_patch(st):
        if st["attempts"][-1]["apply_error"]:
            return "propose_fix" if st["attempt_no"] < max_attempts else "finalize"
        return "validate"

    def after_validate(st):
        v = st["attempts"][-1]["validation"]["verdict"]
        return "propose_fix" if (v in RETRYABLE and st["attempt_no"] < max_attempts) else "finalize"

    return {
        "load_repo": (stop_if_abort("analyze_repo"), ["analyze_repo", "finalize"]),
        "analyze_repo": (stop_if_abort("index_repo"), ["index_repo", "finalize"]),
        "index_repo": (lambda st: "retrieve", ["retrieve"]),
        "retrieve": (after_retrieve, ["diagnose", "finalize"]),
        "diagnose": (after_diagnose, ["propose_fix", "finalize"]),
        "propose_fix": (after_fix, ["apply_patch", "finalize"]),
        "apply_patch": (after_patch, ["validate", "propose_fix", "finalize"]),
        "validate": (after_validate, ["propose_fix", "finalize"]),
    }


# ---------------------------------------------------------------------------- runners

def _run_sequential(nodes, routes, state: PipelineState) -> PipelineState:
    current = "load_repo"
    for _ in range(60):  # hard safety cap against routing loops
        state.update(nodes[current](state))
        if current == "finalize":
            return state
        current = routes[current][0](state)
    raise RuntimeError("workflow did not terminate")  # pragma: no cover


def _run_langgraph(nodes, routes, state: PipelineState) -> PipelineState:
    from langgraph.graph import END, START, StateGraph  # imported lazily: optional dependency

    graph = StateGraph(PipelineState)
    for name, fn in nodes.items():
        graph.add_node(name, fn)
    graph.add_edge(START, "load_repo")
    for name, (router, targets) in routes.items():
        graph.add_conditional_edges(name, router, {t: t for t in targets})
    graph.add_edge("finalize", END)
    app = graph.compile()
    return app.invoke(state, config={"recursion_limit": 60})


def langgraph_available() -> bool:
    try:
        import langgraph  # noqa: F401
        return True
    except ImportError:
        return False


def run_pipeline(deps: Deps, repo_ref: str, issue: str, job_id: str | None = None) -> dict:
    s = deps.settings
    s.workspace_dir.mkdir(parents=True, exist_ok=True)
    workdir = s.workspace_dir / f"job-{job_id or uuid.uuid4().hex[:10]}"
    workdir.mkdir(parents=True, exist_ok=True)
    nodes, routes = make_nodes(deps), make_routes(deps)
    state: PipelineState = {"repo_ref": repo_ref, "issue": issue, "workdir": workdir, "attempts": [],
                            "attempt_no": 0, "timings": {}}
    try:
        if s.use_langgraph and langgraph_available():
            final_state = _run_langgraph(nodes, routes, state)
            runner = "langgraph"
        else:
            final_state = _run_sequential(nodes, routes, state)
            runner = "sequential"
        result = final_state["result"]
        result["runner"] = runner
        return result
    finally:
        if not s.keep_workspace:
            shutil.rmtree(workdir, ignore_errors=True)
