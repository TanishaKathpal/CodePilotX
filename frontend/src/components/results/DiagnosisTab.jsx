import React from "react";
import { Badge, EmptyState, Icon } from "../ui.jsx";

const CONF = { high: "success", medium: "info", low: "warn" };

export default function DiagnosisTab({ result }) {
  const d = result.diagnosis;
  if (!d) {
    const noLlm = result.llm && !result.llm.configured;
    return (
      <EmptyState icon="activity" title={noLlm ? "Diagnosis needs an LLM" : "No diagnosis was produced"}
        actions={noLlm ? <a className="btn btn-secondary btn-sm" href="#/settings">See setup steps</a> : null}>
        {noLlm ? "No LLM is configured, so no root-cause analysis was attempted. The Evidence tab shows the code that retrieval found."
          : result.final.message}
      </EmptyState>
    );
  }
  return (
    <div className="stack">
      <div className="callout">
        <div className="callout-head"><Icon name="activity" size={16} /><strong>Summary</strong>
          <span className="spacer" />
          <Badge tone={CONF[d.confidence] || "neutral"}>Model confidence: {d.confidence}</Badge>
        </div>
        <p>{d.summary}</p>
      </div>
      <div>
        <h3 className="sub">Root cause (the model's hypothesis)</h3>
        <p>{d.root_cause}</p>
        <p className="muted tiny">Confidence is self-reported by the model. The only real evidence is the test result on the Tests tab.</p>
      </div>
      <div>
        <h3 className="sub">Suspected locations</h3>
        <ul className="suspects">
          {d.suspects.map((s, i) => (
            <li key={i}>
              <div className="suspect-top">
                <span className="rank">{i + 1}</span>
                <code>{s.file}</code>{s.symbol && <code className="symbol-code">{s.symbol}</code>}
                <span className="spacer" />
                {s.verified ? <Badge tone="success" icon="check">File exists</Badge> : <Badge tone="danger" icon="x">File not found in repo</Badge>}
              </div>
              {s.reason && <p className="muted small">{s.reason}</p>}
              {s.chunk_ids.length > 0 && <div className="chips">{s.chunk_ids.map((c) => <span key={c} className="chip chip-mono">{c}</span>)}</div>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
