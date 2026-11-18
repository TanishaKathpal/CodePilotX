import React from "react";
import { Badge, Collapsible } from "../ui.jsx";

const LANG_COLORS = ["#6366f1", "#22d3ee", "#8b5cf6", "#34d399", "#fbbf24", "#f472b6", "#94a3b8"];

export default function OverviewTab({ result }) {
  const repo = result.repo;
  if (!repo) return <p className="muted">No repository information is available.</p>;
  const langs = Object.entries(repo.languages).sort((a, b) => b[1].lines - a[1].lines);
  const totalLines = langs.reduce((n, [, v]) => n + v.lines, 0) || 1;
  const maxScore = Math.max(...(result.relevant_files || []).map((f) => f.score), 0.0001);
  const hints = result.hints;
  const hasHints = hints && (hints.files.length || hints.lines.length || hints.identifiers.length);
  return (
    <div className="stack">
      <div className="two-col">
        <div>
          <h3 className="sub">Languages</h3>
          <div className="langbar" role="img" aria-label="Language share by lines of code">
            {langs.map(([k, v], i) => <span key={k} style={{ width: `${(v.lines / totalLines) * 100}%`, background: LANG_COLORS[i % LANG_COLORS.length] }} title={`${k}: ${v.lines} lines`} />)}
          </div>
          <ul className="legend">
            {langs.map(([k, v], i) => (
              <li key={k}><i style={{ background: LANG_COLORS[i % LANG_COLORS.length] }} />{k}<span className="muted"> {v.files} files · {v.lines} lines</span></li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="sub">Detected setup</h3>
          <dl className="kv">
            <dt>Primary language</dt><dd>{repo.primary_language || "unknown"}</dd>
            <dt>Test execution</dt><dd>{repo.validation_supported ? <Badge tone="success">Supported (Python)</Badge> : <Badge tone="neutral">Not supported for this repository</Badge>}</dd>
            <dt>Existing tests</dt><dd>{repo.test_targets.length ? repo.test_targets.map((t) => <code key={t} className="inline">{t}</code>) : <span className="muted">none found</span>}</dd>
            <dt>Key files</dt><dd>{repo.key_files.length ? repo.key_files.map((t) => <code key={t} className="inline">{t}</code>) : <span className="muted">none</span>}</dd>
            {repo.entry_points.length > 0 && <><dt>Entry points</dt><dd>{repo.entry_points.map((t) => <code key={t} className="inline">{t}</code>)}</dd></>}
          </dl>
        </div>
      </div>

      <div>
        <h3 className="sub">Most relevant files</h3>
        {(result.relevant_files || []).length === 0 ? <p className="muted">No files were ranked.</p> : (
          <ul className="filelist">
            {result.relevant_files.map((f) => (
              <li key={f.path}>
                <code>{f.path}</code>
                <span className="bar"><i style={{ width: `${Math.max(6, (f.score / maxScore) * 100)}%` }} /></span>
                <span className="muted tiny">{f.chunks} snippet{f.chunks === 1 ? "" : "s"}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="muted tiny">Bars show relative retrieval score (sum over the file's matching snippets), not bug likelihood.</p>
      </div>

      {hasHints && (
        <div>
          <h3 className="sub">Hints found in your issue</h3>
          <div className="chips">
            {hints.files.map((x) => <span key={"f" + x} className="chip chip-mono">file · {x}</span>)}
            {hints.lines.map((x) => <span key={"l" + x} className="chip chip-mono">line · {x}</span>)}
            {hints.identifiers.map((x) => <span key={"i" + x} className="chip chip-mono">symbol · {x}</span>)}
          </div>
        </div>
      )}

      <Collapsible title="Repository structure" meta={`${repo.structure.length} entries`}>
        <table className="table">
          <tbody>
            {repo.structure.map((r) => (
              <tr key={r.path}><td><code>{r.path}</code></td><td className="muted">{r.files} file{r.files === 1 ? "" : "s"}</td><td className="muted">{r.lines} lines</td></tr>
            ))}
          </tbody>
        </table>
      </Collapsible>
    </div>
  );
}
