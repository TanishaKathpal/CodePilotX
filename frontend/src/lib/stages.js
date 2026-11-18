// The backend reports 8 internal steps; the UI shows 5 stages. This file is the (honest) mapping.

export const STAGES = [
  { id: "scan", title: "Repository Scan", desc: "Fetch, parse and index the code", icon: "folder", steps: ["load_repo", "analyze_repo", "index_repo"], needs: null },
  { id: "retrieval", title: "Code Retrieval", desc: "Find the code relevant to the issue", icon: "search", steps: ["retrieve"], needs: null },
  { id: "diagnosis", title: "Issue Diagnosis", desc: "LLM explains the likely root cause", icon: "activity", steps: ["diagnose"], needs: "llm" },
  { id: "fix", title: "Fix Generation", desc: "LLM proposes a patch and a test", icon: "code", steps: ["propose_fix", "apply_patch"], needs: "llm" },
  { id: "validation", title: "Test Validation", desc: "Run tests before/after in a sandbox", icon: "flask", steps: ["validate"], needs: "sandbox" },
];

export const STATE_LABEL = {
  idle: "Ready", blocked: "Needs setup", pending: "Waiting", running: "Running", done: "Complete",
  failed: "Failed", skipped: "Skipped", unavailable: "Not run", rejected: "Did not pass",
};

// verdict codes (validation.py) that mean "tests ran and the fix was not accepted"
const REJECTED = new Set(["not_reproduced", "fix_failed", "regression", "test_error", "patch_failed"]);
const NOT_RUN = new Set(["not_validated", "run_error"]);

export function deriveStage(stage, steps, ctx) {
  const { jobActive, caps, result } = ctx;
  if (!steps) {
    if (stage.needs === "llm" && !caps.diagnose) return { state: "blocked", detail: "Needs an LLM key" };
    if (stage.needs === "sandbox" && !caps.validate) return { state: "blocked", detail: caps.diagnose ? "Needs the Docker sandbox" : "Needs an LLM key and Docker" };
    return { state: "idle", detail: "" };
  }
  const mine = stage.steps.map((n) => steps.find((s) => s.name === n)).filter(Boolean);
  const statuses = mine.map((s) => s.status);
  const details = mine.map((s) => s.detail).filter(Boolean);
  const detail = details.slice(0, 2).join(" · ");

  if (stage.id === "validation" && statuses.includes("failed")) {
    const code = mine.find((s) => s.status === "failed")?.detail || "";
    if (NOT_RUN.has(code)) return { state: "unavailable", detail: result?.final?.message || "Tests could not be executed" };
    if (REJECTED.has(code)) return { state: "rejected", detail: result?.final?.message || code };
  }
  if (statuses.includes("failed")) return { state: "failed", detail };
  if (statuses.includes("running")) return { state: "running", detail };
  if (statuses.length && statuses.every((s) => s === "done")) return { state: "done", detail };
  if (statuses.length && statuses.every((s) => s === "skipped")) {
    const noLlm = result && result.llm && result.llm.configured === false;
    return { state: "skipped", detail: noLlm && stage.needs ? "No LLM configured" : "" };
  }
  if (statuses.includes("done")) return { state: jobActive ? "running" : "done", detail };
  return { state: "pending", detail: "" };
}
