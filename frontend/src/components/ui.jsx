import React, { useRef, useState } from "react";
import { copyText, downloadTextFile, hasText, parseDiff } from "../lib/format.js";

/* ---------- Icons (inline SVG, no dependency) ---------- */
const ICONS = {
  overview: <><rect x="3" y="3" width="7.5" height="7.5" rx="1.5" /><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5" /><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5" /><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5" /></>,
  analyze: <><circle cx="11" cy="11" r="6.5" /><path d="M20.5 20.5 16 16" /><path d="M9 11h4M11 9v4" /></>,
  history: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2" /></>,
  settings: <><path d="M4 7h9M17 7h3M4 17h3M11 17h9" /><circle cx="15" cy="7" r="2" /><circle cx="9" cy="17" r="2" /></>,
  folder: <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H9l2 2.2h7.5A2.5 2.5 0 0 1 21 9.7v7.8a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5z" />,
  search: <><circle cx="11" cy="11" r="6.5" /><path d="M20.5 20.5 16 16" /></>,
  activity: <path d="M3 12h4l3-8 4 16 3-8h4" />,
  code: <path d="m8 8-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14" />,
  flask: <path d="M9.5 3h5M10.5 3v6L5.2 18.2A1.8 1.8 0 0 0 6.8 21h10.4a1.8 1.8 0 0 0 1.6-2.8L13.5 9V3M8 14h8" />,
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  x: <path d="M6 6l12 12M18 6 6 18" />,
  alert: <><path d="M12 3.5 2.8 19.5h18.4z" /><path d="M12 10v4.2M12 17.4h.01" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5.2M12 7.8h.01" /></>,
  copy: <><rect x="8.5" y="8.5" width="11" height="11" rx="2" /><path d="M15.5 8.5V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7.5a2 2 0 0 0 2 2h2.5" /></>,
  download: <path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19.5h14" />,
  chevron: <path d="m6 9 6 6 6-6" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  refresh: <path d="M20 11a8 8 0 0 0-14.3-4.2L4 9M4 4v5h5M4 13a8 8 0 0 0 14.3 4.2L20 15M20 20v-5h-5" />,
  file: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></>,
  bolt: <path d="M13 2.5 5 13.5h6l-1 8 8-11h-6z" />,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  server: <><rect x="3" y="4" width="18" height="6.5" rx="1.8" /><rect x="3" y="13.5" width="18" height="6.5" rx="1.8" /><path d="M7 7.2h.01M7 16.7h.01" /></>,
  lock: <><rect x="5" y="10.5" width="14" height="10" rx="2" /><path d="M8.5 10.5V7.5a3.5 3.5 0 0 1 7 0v3" /></>,
};

export function Icon({ name, size = 18, className = "" }) {
  const body = ICONS[name];
  if (!body) return null;
  return (
    <svg className={`icon ${className}`} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {body}
    </svg>
  );
}

export function LogoMark({ size = 30 }) {
  return (
    <svg className="logo-mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id="cpx-g" x1="4" y1="4" x2="28" y2="28" gradientUnits="userSpaceOnUse">
          <stop stopColor="#6366f1" /><stop offset="1" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#cpx-g)" />
      <path d="m11.5 11-4.5 5 4.5 5M20.5 11l4.5 5-4.5 5" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="16" cy="16" r="2.2" fill="#67e8f9" />
    </svg>
  );
}

/* ---------- Small building blocks ---------- */
export function Badge({ tone = "neutral", children, icon }) {
  return (
    <span className={`badge badge-${tone}`}>
      {icon && <Icon name={icon} size={12} />}
      {children}
    </span>
  );
}

export function Spinner({ size = 16 }) {
  return <span className="spinner" style={{ width: size, height: size }} role="status" aria-label="Loading" />;
}

export function Card({ title, subtitle, actions, children, className = "", icon }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          <div className="card-title">
            {icon && <span className="card-icon"><Icon name={icon} size={16} /></span>}
            <div>
              <h2>{title}</h2>
              {subtitle && <p className="muted small">{subtitle}</p>}
            </div>
          </div>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Banner({ tone = "info", icon, title, children, actions }) {
  const ic = icon || (tone === "success" ? "check" : tone === "danger" ? "alert" : tone === "warn" ? "alert" : "info");
  return (
    <div className={`banner banner-${tone}`} role={tone === "danger" ? "alert" : "status"}>
      <span className="banner-icon"><Icon name={ic} size={18} /></span>
      <div className="banner-body">
        {title && <strong>{title}</strong>}
        {children && <div className="banner-text">{children}</div>}
      </div>
      {actions && <div className="banner-actions">{actions}</div>}
    </div>
  );
}

export function EmptyState({ icon = "info", title, children, actions }) {
  return (
    <div className="empty">
      <span className="empty-icon"><Icon name={icon} size={22} /></span>
      <h3>{title}</h3>
      {children && <div className="muted">{children}</div>}
      {actions && <div className="empty-actions">{actions}</div>}
    </div>
  );
}

export function CopyButton({ text, label = "Copy" }) {
  const [state, setState] = useState("idle");
  const timer = useRef(null);
  const onClick = async () => {
    const ok = await copyText(text);
    setState(ok ? "done" : "fail");
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), 1600);
  };
  return (
    <button type="button" className="btn btn-ghost btn-sm" onClick={onClick} aria-label={`${label} to clipboard`}>
      <Icon name={state === "done" ? "check" : "copy"} size={14} />
      {state === "done" ? "Copied" : state === "fail" ? "Copy failed" : label}
    </button>
  );
}

export function DownloadButton({ content, filename, label = "Download tests" }) {
  const [state, setState] = useState("idle");
  const timer = useRef(null);
  const unavailable = !hasText(content);
  const onClick = () => {
    if (unavailable) return;
    const ok = downloadTextFile(filename, content);
    setState(ok ? "done" : "fail");
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), 1600);
  };
  return (
    <button type="button" className="btn btn-ghost btn-sm" onClick={onClick} disabled={unavailable}
      title={unavailable ? "No generated test code to download" : `Save as ${filename}`}
      aria-label={unavailable ? `${label} (unavailable: no test code)` : `${label} as ${filename}`}>
      <Icon name={state === "done" ? "check" : "download"} size={14} />
      {state === "done" ? "Downloaded" : state === "fail" ? "Download failed" : label}
    </button>
  );
}

export function Tabs({ tabs, active, onChange, idPrefix = "tab" }) {
  const refs = useRef([]);
  const onKey = (e, i) => {
    let next = null;
    if (e.key === "ArrowRight") next = (i + 1) % tabs.length;
    if (e.key === "ArrowLeft") next = (i - 1 + tabs.length) % tabs.length;
    if (e.key === "Home") next = 0;
    if (e.key === "End") next = tabs.length - 1;
    if (next !== null) {
      e.preventDefault();
      onChange(tabs[next].id);
      refs.current[next]?.focus();
    }
  };
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t, i) => (
        <button key={t.id} ref={(el) => (refs.current[i] = el)} role="tab" type="button"
          id={`${idPrefix}-${t.id}`} aria-selected={active === t.id} aria-controls={`${idPrefix}-panel`}
          tabIndex={active === t.id ? 0 : -1} className={`tab ${active === t.id ? "on" : ""}`}
          onClick={() => onChange(t.id)} onKeyDown={(e) => onKey(e, i)}>
          {t.icon && <Icon name={t.icon} size={15} />}
          {t.label}
          {t.count !== undefined && t.count !== null && <span className="tab-count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Collapsible({ title, meta, defaultOpen = false, children, className = "" }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <details className={`collapsible ${className}`} open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>
        <span className="collapsible-title">{title}</span>
        {meta && <span className="collapsible-meta">{meta}</span>}
        <Icon name="chevron" size={16} className="chev" />
      </summary>
      <div className="collapsible-body">{children}</div>
    </details>
  );
}

/* ---------- Code & diff viewers.
   Repository text is untrusted: it is only ever rendered as React text children (auto-escaped). ---------- */
export function CodeBlock({ code, startLine = 1, maxHeight = 340, copy = true, truncated = false, download = null }) {
  const text = (code ?? "").replace(/\n$/, "");
  const lines = text.split("\n");
  return (
    <div className="codeblock">
      {(copy || download) && (
        <div className="codeblock-tools">
          {copy && <CopyButton text={text} />}
          {/* Download uses the RAW code (not `text`, which drops the final newline) so the file is exact. */}
          {download && <DownloadButton content={typeof code === "string" ? code : ""} filename={download.filename} />}
        </div>
      )}
      <pre style={{ maxHeight }} tabIndex={0}>
        <code>
          {lines.map((l, i) => (
            <div className="cl" key={i}>
              <span className="ln">{startLine + i}</span>
              <span className="lt">{l === "" ? " " : l}</span>
            </div>
          ))}
          {truncated && <div className="cl"><span className="ln" /><span className="lt muted">… (truncated)</span></div>}
        </code>
      </pre>
    </div>
  );
}

export function DiffView({ diff, maxHeight = 420 }) {
  const rows = parseDiff(diff);
  return (
    <div className="codeblock diff">
      <div className="codeblock-tools"><CopyButton text={diff} label="Copy diff" /></div>
      <pre style={{ maxHeight }} tabIndex={0}>
        <code>
          {rows.map((r, i) =>
            r.type === "file" || r.type === "hunk" ? (
              <div key={i} className={`cl d-${r.type}`}><span className="ln" /><span className="ln" /><span className="lt">{r.text}</span></div>
            ) : (
              <div key={i} className={`cl d-${r.type}`}>
                <span className="ln">{r.oldNo ?? ""}</span>
                <span className="ln">{r.newNo ?? ""}</span>
                <span className="lt"><i className="sign">{r.type === "add" ? "+" : r.type === "del" ? "−" : " "}</i>{r.text === "" ? " " : r.text}</span>
              </div>
            ))}
        </code>
      </pre>
    </div>
  );
}
