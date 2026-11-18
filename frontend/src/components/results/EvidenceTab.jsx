import React from "react";
import { Badge, CodeBlock, Collapsible, EmptyState } from "../ui.jsx";

export default function EvidenceTab({ evidence }) {
  if (!evidence || evidence.length === 0) {
    return <EmptyState icon="search" title="No code was retrieved">The repository could not be indexed, or no chunks matched. See the Notes tab for warnings.</EmptyState>;
  }
  const max = Math.max(...evidence.map((e) => e.score), 0.0001);
  return (
    <div className="stack-sm">
      <p className="muted small">
        {evidence.length} snippets found by vector search plus hints from your issue. IDs (C1, C2…) are the same ones the LLM is shown.
        Scores are relative ranking values, not probabilities.
      </p>
      {evidence.map((e, idx) => (
        <Collapsible key={e.id} defaultOpen={idx === 0} className="evidence"
          title={<><span className="eid">{e.id}</span><code className="path">{e.path}</code><span className="muted tiny"> :{e.start_line}–{e.end_line}</span>{e.name && <span className="symbol">{e.name}</span>}</>}
          meta={<><span className="bar sm"><i style={{ width: `${Math.max(6, (e.score / max) * 100)}%` }} /></span><span className="score">{e.score}</span></>}>
          <div className="chips">
            {e.reasons.map((r, i) => <span key={i} className="chip">{r}</span>)}
            {!e.sent_to_llm && <Badge tone="warn">Not sent to the LLM (context limit)</Badge>}
          </div>
          <CodeBlock code={e.code} startLine={e.start_line} truncated={e.truncated} maxHeight={300} />
        </Collapsible>
      ))}
    </div>
  );
}
