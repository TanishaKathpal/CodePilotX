import React, { useState } from "react";
import { Banner, Card, Tabs } from "../ui.jsx";
import OverviewTab from "./OverviewTab.jsx";
import EvidenceTab from "./EvidenceTab.jsx";
import DiagnosisTab from "./DiagnosisTab.jsx";
import PatchTab from "./PatchTab.jsx";
import TestsTab from "./TestsTab.jsx";
import NotesTab, { noteCount } from "./NotesTab.jsx";
import { totalSeconds } from "../../lib/format.js";

// One place decides what the user is told about the outcome. "validated" is shown ONLY when
// the backend reports verified_fix === true (tests really failed before and passed after, in the sandbox).
export function describeOutcome(final) {
  if (final.verified_fix) return { tone: "success", title: "Fix validated by tests" };
  if (final.status === "failed") return { tone: "danger", title: "Analysis could not complete" };
  if (final.status === "retrieval_only") return { tone: "info", title: "Analysis only: no LLM configured" };
  if (final.status === "partial") return { tone: "warn", title: "Partial result" };
  if (final.verdict === "not_validated" || final.verdict === "run_error") return { tone: "warn", title: "Suggested fix, not validated" };
  return { tone: "danger", title: "Suggested fix did not pass validation" };
}

function Stat({ label, value }) {
  return <div className="statbox" title={`${label}: ${value}`}><div className="statbox-v">{value}</div><div className="statbox-l">{label}</div></div>;
}

export default function ResultsView({ job, readiness }) {
  const result = job.result;
  const [tab, setTab] = useState(result.attempts.length ? "patch" : result.diagnosis ? "diagnosis" : "evidence");
  const [sel, setSel] = useState(Math.max(0, result.attempts.length - 1));
  const out = describeOutcome(result.final);
  const repo = result.repo;
  const secs = totalSeconds(result.timings);
  const needsLlm = result.final.status === "retrieval_only";
  const needsSandbox = ["not_validated", "run_error"].includes(result.final.verdict) && !readiness.caps.validate && readiness.caps.diagnose;

  const tabs = [
    { id: "overview", label: "Repository", icon: "folder" },
    { id: "evidence", label: "Evidence", icon: "search", count: result.evidence.length },
    { id: "diagnosis", label: "Diagnosis", icon: "activity" },
    { id: "patch", label: "Patch", icon: "code", count: result.attempts.length || null },
    { id: "tests", label: "Tests", icon: "flask" },
    { id: "notes", label: "Notes", icon: "info", count: noteCount(result) || null },
  ];

  return (
    <div className="results fade-in">
      <Banner tone={out.tone} title={out.title}
        actions={(needsLlm || needsSandbox) ? <a className="btn btn-secondary btn-sm" href="#/settings">Setup steps</a> : null}>
        {result.final.message}
      </Banner>
      {repo && (
        <div className="statrow">
          <Stat label="Files" value={repo.file_count} />
          <Stat label="Lines" value={repo.line_count.toLocaleString()} />
          <Stat label="Language" value={repo.primary_language || "n/a"} />
          <Stat label="Symbols" value={repo.symbol_count} />
          <Stat label="Chunks indexed" value={repo.chunk_count} />
          <Stat label="Model" value={result.llm.model || "none"} />
          {secs !== null && <Stat label="Pipeline time" value={`${secs}s`} />}
        </div>
      )}
      <Card className="results-card">
        <Tabs tabs={tabs} active={tab} onChange={setTab} idPrefix="res" />
        <div role="tabpanel" id="res-panel" aria-labelledby={`res-${tab}`} className="tabpanel">
          {tab === "overview" && <OverviewTab result={result} />}
          {tab === "evidence" && <EvidenceTab evidence={result.evidence} />}
          {tab === "diagnosis" && <DiagnosisTab result={result} />}
          {tab === "patch" && <PatchTab result={result} sel={sel} setSel={setSel} />}
          {tab === "tests" && <TestsTab result={result} sel={sel} setSel={setSel} />}
          {tab === "notes" && <NotesTab result={result} />}
        </div>
      </Card>
    </div>
  );
}
