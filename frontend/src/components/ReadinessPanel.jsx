import React from "react";
import { Badge, Card, CopyButton, Icon } from "./ui.jsx";

const TONE_BADGE = { success: "success", warn: "warn", info: "info", neutral: "neutral", danger: "danger" };

function Item({ icon, name, st }) {
  return (
    <div className={`ready-item tone-${st.tone}`}>
      <div className="ready-top">
        <span className="ready-icon"><Icon name={icon} size={16} /></span>
        <strong>{name}</strong>
        <Badge tone={TONE_BADGE[st.tone]}>{st.value}</Badge>
      </div>
      <p className="muted small">{st.detail}</p>
      {st.note && <p className="muted tiny">{st.note}</p>}
      {st.fix && (
        <div className="fix">
          <div className="fix-title">{st.fix.title}</div>
          <ol>{st.fix.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
          {st.fix.snippet && (
            <div className="snippet"><code>{st.fix.snippet}</code><CopyButton text={st.fix.snippet} /></div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ReadinessPanel({ readiness, title = "System readiness", subtitle }) {
  return (
    <Card title={title} subtitle={subtitle} icon="server">
      <div className="ready-grid">
        <Item icon="server" name="Backend API" st={readiness.backend} />
        <Item icon="bolt" name="LLM" st={readiness.llm} />
        <Item icon="flask" name="Test sandbox" st={readiness.sandbox} />
        <Item icon="activity" name="Agent orchestrator" st={readiness.orchestrator} />
        <Item icon="search" name="Embeddings" st={readiness.embeddings} />
      </div>
    </Card>
  );
}
