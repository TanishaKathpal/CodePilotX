import React, { useEffect, useState } from "react";
import { Banner, Card, EmptyState, Icon } from "../components/ui.jsx";
import { repoLabel } from "../lib/format.js";
import AnalyzeForm from "../components/AnalyzeForm.jsx";
import WorkflowTracker from "../components/WorkflowTracker.jsx";
import ResultsView from "../components/results/ResultsView.jsx";

export default function AnalyzeView({ form, readiness, job, busy, error, onDismissError }) {
  const active = job && (job.status === "queued" || job.status === "running");
  // Once a run starts, fold the form into a one-line summary so the results are not pushed off-screen.
  const [editing, setEditing] = useState(!job);
  useEffect(() => { if (busy) setEditing(false); }, [busy]);
  const showForm = editing || !job;
  return (
    <div className="page">
      {error && (
        <Banner tone="danger" title="Something went wrong" actions={<button type="button" className="btn btn-secondary btn-sm" onClick={onDismissError}>Dismiss</button>}>
          {error}
        </Banner>
      )}
      {showForm ? (
        <Card title="Analyze a repository" subtitle="Public GitHub repositories, or a bundled sample task" icon="analyze">
          <AnalyzeForm {...form} busy={busy} caps={readiness.caps} />
        </Card>
      ) : (
        <Card className="summary-card">
          <div className="runsum">
            <div className="runsum-main">
              <span className="chip"><Icon name="folder" size={13} />{repoLabel(job.repo)}</span>
              <p className="muted small clamp-2">{job.issue}</p>
            </div>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(true)} disabled={busy}>New analysis</button>
          </div>
        </Card>
      )}

      <Card title="Workflow" icon="activity"
        subtitle={active ? "Analysis in progress…" : job ? "Finished" : "Five stages, from scanning to validation"}>
        <WorkflowTracker job={job} caps={readiness.caps} />
      </Card>

      {job && job.status === "failed" && (
        <Banner tone="danger" title="The analysis failed">{job.error}</Banner>
      )}
      {active && (
        <Card className="skeleton-card" aria-busy="true">
          <div className="skeleton w60" /><div className="skeleton w90" /><div className="skeleton w75" />
          <p className="muted small">Results will appear here when the run completes.</p>
        </Card>
      )}
      {job && job.status === "done" && job.result && <ResultsView key={job.id} job={job} readiness={readiness} />}
      {!job && !error && (
        <EmptyState icon="analyze" title="No analysis yet">
          Choose a sample task above to try the app without a GitHub URL, or enter your own repository and issue.
        </EmptyState>
      )}
    </div>
  );
}
