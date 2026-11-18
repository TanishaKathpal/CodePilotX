import React from "react";
import { Badge, Card, EmptyState } from "../components/ui.jsx";
import { repoLabel } from "../lib/format.js";

export default function HistoryView({ job }) {
  return (
    <div className="page">
      <EmptyState icon="history" title="Analysis history is coming soon"
        actions={<a className="btn btn-primary btn-sm" href="#/analyze">Run an analysis</a>}>
        The backend keeps jobs in memory only and has no endpoint for listing past runs, so there is nothing to show yet.
        Persistent history needs a backend change (storage plus a list endpoint).
      </EmptyState>
      {job && (
        <Card title="This session" subtitle="Your most recent run, kept only while this page stays open" icon="history">
          <div className="lastrun">
            <code>{repoLabel(job.repo)}</code>
            <Badge tone={job.status === "done" ? "success" : job.status === "failed" ? "danger" : "info"}>
              {job.status === "done" ? "Finished" : job.status === "failed" ? "Failed" : "In progress"}
            </Badge>
            <span className="muted small issue-snippet">{job.issue.length > 140 ? job.issue.slice(0, 140) + "…" : job.issue}</span>
            <a className="btn btn-secondary btn-sm" href="#/analyze">Open</a>
          </div>
        </Card>
      )}
    </div>
  );
}
