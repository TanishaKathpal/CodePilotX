import React from "react";
import { Banner, DiffView, EmptyState } from "../ui.jsx";
import AttemptPicker from "./AttemptPicker.jsx";

export default function PatchTab({ result, sel, setSel }) {
  const attempts = result.attempts;
  if (!attempts.length) {
    const noLlm = result.llm && !result.llm.configured;
    return (
      <EmptyState icon="code" title="No patch was generated"
        actions={noLlm ? <a className="btn btn-secondary btn-sm" href="#/settings">See setup steps</a> : null}>
        {noLlm ? "Fix generation needs an LLM, and none is configured." : result.final.message}
      </EmptyState>
    );
  }
  const a = attempts[Math.min(sel, attempts.length - 1)];
  const validated = result.final.verified_fix && a.validation && a.validation.verdict === "validated";
  return (
    <div className="stack">
      <AttemptPicker attempts={attempts} value={sel} onChange={setSel} />
      {!validated && (
        <Banner tone="warn" title="This patch is a proposal">
          It has not been shown to fix the issue. Review it and run your own tests before using it.
        </Banner>
      )}
      <div>
        <h3 className="sub">Why this change</h3>
        <p>{a.explanation}</p>
      </div>
      <div>
        <h3 className="sub">Proposed diff</h3>
        {a.apply_error && <Banner tone="danger" title="The edit could not be applied">{a.apply_error}</Banner>}
        {a.diff ? <DiffView diff={a.diff} /> : !a.apply_error && <p className="muted">No diff available.</p>}
      </div>
    </div>
  );
}
