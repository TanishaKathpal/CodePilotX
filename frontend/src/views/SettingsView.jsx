import React from "react";
import { Banner, Card, CopyButton } from "../components/ui.jsx";
import ReadinessPanel from "../components/ReadinessPanel.jsx";

const ENV = [
  ["LLM_PROVIDER", "anthropic or openai_compatible"],
  ["LLM_MODEL", "Model id your provider supports"],
  ["ANTHROPIC_API_KEY / OPENAI_API_KEY", "Credentials (environment only, never stored by the UI)"],
  ["EMBEDDING_BACKEND", "hashing (offline) or sentence-transformers"],
  ["SANDBOX_IMAGE, SANDBOX_MEMORY, SANDBOX_CPUS, SANDBOX_TIMEOUT_S", "Test sandbox limits"],
  ["MAX_FIX_ATTEMPTS, USE_LANGGRAPH", "Agent behaviour"],
];
const RUN = "cd backend\nuvicorn app.main:app --reload --port 8000";

export default function SettingsView({ health, readiness, offline }) {
  return (
    <div className="page">
      <Banner tone="info" title="Settings are read-only here">
        The backend has no settings API, and API keys must never pass through a browser. Edit <code className="inline">.env</code> in the
        project root and restart the backend; this page then shows what the backend reports.
      </Banner>
      <ReadinessPanel readiness={readiness} title="Live configuration" subtitle="As reported by GET /api/health" />
      {health && (
        <Card title="Reported values" icon="server">
          <dl className="kv wide">
            <dt>LLM provider</dt><dd>{health.llm.provider}</dd>
            <dt>LLM model</dt><dd><code className="inline">{health.llm.model}</code></dd>
            <dt>LLM key</dt><dd>{health.llm.configured ? "detected" : "not set"}</dd>
            <dt>Sandbox image</dt><dd><code className="inline">{health.sandbox.image}</code></dd>
            <dt>Sandbox status</dt><dd>{health.sandbox.available ? "ready" : health.sandbox.detail}</dd>
            <dt>Embeddings</dt><dd>{health.embedding_backend}</dd>
            <dt>Orchestrator</dt><dd>{health.orchestrator}</dd>
          </dl>
        </Card>
      )}
      {offline && <Banner tone="danger" title="Backend offline">Start the backend, then use the refresh button in the header.</Banner>}
      <Card title="Configuration reference" subtitle="Set these in .env (see .env.example for the full list)" icon="settings">
        <ul className="envlist">{ENV.map(([k, v]) => <li key={k}><code>{k}</code><span className="muted small">{v}</span></li>)}</ul>
        <div className="snippet block"><pre><code>{RUN}</code></pre><CopyButton text={RUN} /></div>
      </Card>
    </div>
  );
}
