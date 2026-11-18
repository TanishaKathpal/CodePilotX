import React from "react";
import { Badge, Icon, LogoMark } from "./ui.jsx";

const NAV = [
  { id: "overview", label: "Overview", icon: "overview" },
  { id: "analyze", label: "Analyze Repository", icon: "analyze" },
  { id: "history", label: "Analysis History", icon: "history", soon: true },
  { id: "settings", label: "Settings", icon: "settings" },
];

export default function Sidebar({ view, open, onClose }) {
  return (
    <>
      <div className={`scrim ${open ? "show" : ""}`} onClick={onClose} aria-hidden="true" />
      <aside className={`sidebar ${open ? "open" : ""}`} aria-label="Primary">
        <div className="brand">
          <LogoMark />
          <div>
            <div className="brand-name">CodePilot<span>X</span></div>
            <div className="brand-sub">Agentic code intelligence</div>
          </div>
        </div>
        <nav>
          {NAV.map((n) => (
            <a key={n.id} href={`#/${n.id}`} className={`nav-item ${view === n.id ? "active" : ""}`}
              aria-current={view === n.id ? "page" : undefined} onClick={onClose}>
              <Icon name={n.icon} size={18} />
              <span>{n.label}</span>
              {n.soon && <Badge tone="neutral">Soon</Badge>}
            </a>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="foot-card">
            <Icon name="lock" size={15} />
            <p>Repository code is treated as untrusted. Tests only ever run inside an isolated Docker container.</p>
          </div>
          <div className="muted tiny">CodePilotX · local instance</div>
        </div>
      </aside>
    </>
  );
}
