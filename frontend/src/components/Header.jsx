import React from "react";
import { Icon } from "./ui.jsx";
import { repoLabel } from "../lib/format.js";

const TITLES = { overview: "Overview", analyze: "Analyze Repository", history: "Analysis History", settings: "Settings" };

function Pill({ label, value, tone, onClick, title }) {
  return (
    <button type="button" className={`pill pill-${tone}`} onClick={onClick} title={title}>
      <span className={`dot dot-${tone}`} aria-hidden="true" />
      <span className="pill-label">{label}</span>
      <span className="pill-value">{value}</span>
    </button>
  );
}

export default function Header({ view, readiness, job, onMenu, onRefresh, refreshing }) {
  const goSettings = () => { window.location.hash = "#/settings"; };
  const ws = job ? repoLabel(job.repo) : "";
  return (
    <header className="topbar">
      <button type="button" className="icon-btn menu-btn" onClick={onMenu} aria-label="Open navigation">
        <Icon name="menu" />
      </button>
      <div className="topbar-left">
        <h1 className="page-title">{TITLES[view]}</h1>
        <span className="chip" title="The repository of the most recent analysis in this session">
          <Icon name="folder" size={13} />
          {ws ? ws : "No repository analyzed yet"}
        </span>
      </div>
      <div className="topbar-right" aria-live="polite">
        <Pill label="Backend" value={readiness.backend.value} tone={readiness.backend.tone} onClick={goSettings} title={readiness.backend.detail} />
        <Pill label="LLM" value={readiness.llm.value} tone={readiness.llm.tone} onClick={goSettings} title={readiness.llm.detail} />
        <Pill label="Sandbox" value={readiness.sandbox.value} tone={readiness.sandbox.tone} onClick={goSettings} title={readiness.sandbox.detail} />
        <button type="button" className={`icon-btn ${refreshing ? "spin" : ""}`} onClick={onRefresh} aria-label="Refresh status" title="Refresh status">
          <Icon name="refresh" size={16} />
        </button>
      </div>
    </header>
  );
}
