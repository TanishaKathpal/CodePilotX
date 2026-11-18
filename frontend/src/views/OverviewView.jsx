import React from "react";
import { Badge, Card, Icon } from "../components/ui.jsx";
import AnalyzeForm from "../components/AnalyzeForm.jsx";
import WorkflowTracker from "../components/WorkflowTracker.jsx";
import ReadinessPanel from "../components/ReadinessPanel.jsx";
import { describeOutcome } from "../components/results/ResultsView.jsx";
import { repoLabel } from "../lib/format.js";

export default function OverviewView({ form, readiness, job, busy }) {
  const done = job && job.status === "done" && job.result;
  const out = done ? describeOutcome(job.result.final) : null;
  return (
    <div className="page">
      <section className="hero">
        <div>
          <p className="eyebrow">Agentic AI code intelligence</p>
          <h2 className="hero-title">Find the bug. Propose the fix. Prove it with a test.</h2>
          <p className="hero-sub">
            Point CodePilotX at a public repository and describe the problem. It reads the code, retrieves the parts that matter,
            diagnoses the likely cause, drafts a patch and a test, and checks the result in an isolated sandbox. It only calls a fix
            “validated” when the tests really passed.
          </p>
        </div>
      </section>

      <div className="grid-2">
        <Card title="New analysis" subtitle="Enter a repository and describe the issue" icon="analyze">
          <AnalyzeForm {...form} busy={busy} caps={readiness.caps} compact />
        </Card>
        <div className="stack">
          <Card title="What will run" subtitle="Based on your current setup" icon="activity">
            <WorkflowTracker job={null} caps={readiness.caps} compact />
          </Card>
          {job && (
            <Card title="Latest run (this session)" icon="history">
              <div className="lastrun">
                <code>{repoLabel(job.repo)}</code>
                {done ? <Badge tone={out.tone === "danger" ? "danger" : out.tone}>{out.title}</Badge>
                  : job.status === "failed" ? <Badge tone="danger">Failed</Badge> : <Badge tone="info">In progress</Badge>}
                <a className="btn btn-secondary btn-sm" href="#/analyze">Open <Icon name="arrow" size={14} /></a>
              </div>
            </Card>
          )}
        </div>
      </div>

      <ReadinessPanel readiness={readiness} subtitle="Live status from the backend. Missing pieces limit what an analysis can do; they never block the app." />
    </div>
  );
}
