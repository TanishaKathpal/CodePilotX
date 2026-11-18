import React from "react";

export default function AttemptPicker({ attempts, value, onChange }) {
  if (attempts.length < 2) return null;
  return (
    <div className="segmented" role="group" aria-label="Fix attempt">
      <span className="muted small">Attempt</span>
      {attempts.map((a, i) => (
        <button key={a.n} type="button" className={i === value ? "on" : ""} onClick={() => onChange(i)}>
          {a.n}<span className="seg-sub">{a.validation ? a.validation.verdict.replace(/_/g, " ") : a.apply_error ? "patch failed" : "—"}</span>
        </button>
      ))}
    </div>
  );
}
