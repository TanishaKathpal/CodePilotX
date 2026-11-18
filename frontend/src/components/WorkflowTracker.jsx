import React from "react";
import { Icon, Spinner } from "./ui.jsx";
import { STAGES, STATE_LABEL, deriveStage } from "../lib/stages.js";

function StageIcon({ state, icon }) {
  if (state === "running") return <Spinner size={16} />;
  if (state === "done") return <Icon name="check" size={16} />;
  if (state === "failed" || state === "rejected") return <Icon name="x" size={16} />;
  if (state === "unavailable" || state === "blocked") return <Icon name={icon} size={16} />;
  return <Icon name={icon} size={16} />;
}

export default function WorkflowTracker({ job, caps, compact = false }) {
  const steps = job ? job.steps : null;
  const jobActive = !!job && (job.status === "queued" || job.status === "running");
  const ctx = { jobActive, caps, result: job ? job.result : null };
  const attempt = job && job.steps.find((s) => s.name === "propose_fix")?.detail;
  return (
    <ol className={`tracker ${compact ? "compact" : ""}`} aria-label="Analysis workflow">
      {STAGES.map((st, i) => {
        const { state, detail } = deriveStage(st, steps, ctx);
        const shown = state === "running" && st.id === "fix" && attempt ? attempt : detail;
        return (
          <li key={st.id} className={`stage stage-${state}`} aria-current={state === "running" ? "step" : undefined}>
            <div className="stage-node"><StageIcon state={state} icon={st.icon} /></div>
            <div className="stage-body">
              <div className="stage-title">
                <span className="stage-num">{i + 1}</span>{st.title}
              </div>
              <div className="stage-state">{STATE_LABEL[state]}</div>
              <div className="stage-detail" title={shown}>{shown || (compact ? "" : st.desc)}</div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
