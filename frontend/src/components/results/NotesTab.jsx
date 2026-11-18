import React from "react";
import { Banner, Card } from "../ui.jsx";

const LIMITS = [
  "Automated test execution supports Python repositories (pytest) only. Other languages get analysis and a suggested diff, never a validated status.",
  "The sandbox has no network and only pytest installed, so tests that need third-party packages (numpy, django…) cannot run unless you add them to the sandbox image.",
  "“Validated” means a generated test failed before the change and passed after it, with no regressions, inside the sandbox. It does not prove the fix is semantically perfect.",
  "The default embeddings match on shared words, not deep meaning. Issues that share no vocabulary with the code can be missed.",
  "Model confidence is self-reported and not evidence. Repositories are limited in size (see backend limits); oversized repos are rejected or partially indexed with a warning.",
];

export function noteCount(result) {
  return (result.warnings || []).length + ((result.repo && result.repo.notes) || []).filter((n) => !(result.warnings || []).includes(n)).length + (result.notes || []).length;
}

export default function NotesTab({ result }) {
  const warnings = result.warnings || [];
  const repoNotes = ((result.repo && result.repo.notes) || []).filter((n) => !warnings.includes(n));
  const notes = result.notes || [];
  const none = warnings.length + repoNotes.length + notes.length === 0;
  return (
    <div className="stack">
      <div className="stack-sm">
        {none && <Banner tone="info" title="No warnings for this run" />}
        {warnings.map((w, i) => <Banner key={"w" + i} tone="warn" title="Repository warning">{w}</Banner>)}
        {repoNotes.map((w, i) => <Banner key={"r" + i} tone="info" title="Repository note">{w}</Banner>)}
        {notes.map((w, i) => <Banner key={"n" + i} tone="warn" title="About this result">{w}</Banner>)}
      </div>
      <Card title="Known limitations" subtitle="General to CodePilotX, not specific to this run" icon="info">
        <ul className="limits">{LIMITS.map((l, i) => <li key={i}>{l}</li>)}</ul>
      </Card>
    </div>
  );
}
