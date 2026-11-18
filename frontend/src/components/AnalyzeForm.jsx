import React, { useState } from "react";
import { Icon, Spinner } from "./ui.jsx";
import { ISSUE_MAX, validateIssue, validateRepo } from "../lib/format.js";

export default function AnalyzeForm({ repo, setRepo, issue, setIssue, samples, samplesError, onSubmit, busy, caps, compact = false }) {
  const [touched, setTouched] = useState({ repo: false, issue: false });
  const r = validateRepo(repo);
  const i = validateIssue(issue);
  const canSubmit = r.ok && i.ok && !busy;
  const selected = samples.find((s) => s.repo === repo.trim() && s.issue === issue.trim());

  const pick = (s) => {
    setRepo(s.repo);
    setIssue(s.issue);
    setTouched({ repo: false, issue: false });
  };
  const submit = (e) => {
    e.preventDefault();
    setTouched({ repo: true, issue: true });
    if (canSubmit) onSubmit(repo.trim(), issue.trim());
  };

  const limited = [];
  if (!caps.diagnose) limited.push("diagnosis and fix generation (needs an LLM key)");
  if (!caps.validate) limited.push("test validation (needs the Docker sandbox" + (caps.diagnose ? "" : " and an LLM key") + ")");

  return (
    <form className="form" onSubmit={submit} noValidate>
      {samples.length > 0 && (
        <div className="field">
          <div className="label-row"><span className="label">Start from a sample task</span><span className="muted tiny">Bundled repos with a real planted bug</span></div>
          <div className="samples" role="group" aria-label="Sample tasks">
            {samples.map((s) => (
              <button key={s.id} type="button" className={`sample ${selected && selected.id === s.id ? "on" : ""}`} onClick={() => pick(s)} disabled={busy}>
                <span className="sample-id">{s.id.replace(/-/g, " ")}</span>
                <span className="sample-meta">{s.repo} · {(s.difficulty || "").split(" ")[0]}</span>
              </button>
            ))}
          </div>
        </div>
      )}
      {samplesError && <p className="muted small">Sample tasks are unavailable: {samplesError}</p>}

      <div className="field">
        <label className="label" htmlFor="repo">Repository</label>
        <div className={`input-wrap ${touched.repo && repo && !r.ok ? "invalid" : ""}`}>
          <Icon name="folder" size={16} />
          <input id="repo" value={repo} onChange={(e) => setRepo(e.target.value)} onBlur={() => setTouched((t) => ({ ...t, repo: true }))}
            placeholder="https://github.com/owner/repo   or   sample:bank" autoComplete="off" spellCheck="false" disabled={busy} />
        </div>
        {touched.repo && r.hint && <p className="hint bad">{r.hint}</p>}
        {!r.hint && <p className="hint">Public GitHub repositories only. Python repositories get the full pipeline; other languages get analysis without test execution.</p>}
      </div>

      <div className="field">
        <label className="label" htmlFor="issue">Coding issue or stack trace</label>
        <textarea id="issue" rows={compact ? 5 : 7} value={issue} onChange={(e) => setIssue(e.target.value)} onBlur={() => setTouched((t) => ({ ...t, issue: true }))}
          className={touched.issue && issue && !i.ok ? "invalid" : ""} disabled={busy} spellCheck="false"
          placeholder={"Describe the wrong behaviour, or paste an error / traceback.\ne.g. withdraw(50) raises InsufficientFunds when the balance is exactly 50"} />
        <div className="label-row">
          {touched.issue && i.hint ? <p className="hint bad">{i.hint}</p> : <p className="hint">Mention function names, file paths or traceback lines when you know them: retrieval uses them.</p>}
          <span className={`counter ${issue.trim().length > ISSUE_MAX ? "bad" : ""}`}>{issue.trim().length} / {ISSUE_MAX}</span>
        </div>
      </div>

      <div className="form-foot">
        <p className="muted small capline">
          {limited.length === 0
            ? "Full pipeline available: scan, retrieval, diagnosis, fix generation and sandboxed test validation."
            : <>Will run: repository scan and code retrieval. Not available yet: {limited.join("; ")}.</>}
        </p>
        <button type="submit" className="btn btn-primary" disabled={!canSubmit} aria-busy={busy}>
          {busy ? <><Spinner size={15} /> Analyzing…</> : <><Icon name="bolt" size={16} /> Analyze Repository</>}
        </button>
      </div>
    </form>
  );
}
