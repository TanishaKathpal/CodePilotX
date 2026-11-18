import React from "react";
import { Badge, Banner, CodeBlock, Collapsible, DownloadButton, EmptyState, Icon } from "../ui.jsx";
import { hasText } from "../../lib/format.js";
import AttemptPicker from "./AttemptPicker.jsx";

function RunCard({ title, subtitle, run }) {
  if (!run) return null;
  if (!run.ran) {
    return (
      <div className="run run-off">
        <div className="run-head"><strong>{title}</strong><Badge tone="warn">Did not run</Badge></div>
        <p className="muted small">{run.error || "The tests could not be executed."}</p>
      </div>
    );
  }
  const bad = run.failed + run.errors;
  return (
    <div className="run">
      <div className="run-head"><strong>{title}</strong><span className="muted tiny">{run.duration_s}s</span></div>
      <p className="muted tiny">{subtitle}</p>
      <div className="stats">
        <span className="stat ok"><b>{run.passed}</b> passed</span>
        <span className={`stat ${bad ? "bad" : ""}`}><b>{run.failed}</b> failed</span>
        <span className={`stat ${run.errors ? "bad" : ""}`}><b>{run.errors}</b> errors</span>
        <span className="stat"><b>{run.skipped}</b> skipped</span>
      </div>
      <Collapsible title="Individual tests" meta={`${run.tests.length} shown`}>
        <ul className="testlist">
          {run.tests.map((t) => (
            <li key={t.id} className={`t-${t.status}`}>
              <Icon name={t.status === "passed" ? "check" : t.status === "skipped" ? "info" : "x"} size={14} />
              <code>{t.id}</code>
              <span className="muted tiny">{t.status}</span>
              {t.message && <span className="tmsg muted tiny">{t.message}</span>}
            </li>
          ))}
        </ul>
        {run.output_tail && <><p className="muted tiny">Raw output (tail)</p><CodeBlock code={run.output_tail} maxHeight={220} /></>}
      </Collapsible>
    </div>
  );
}

export default function TestsTab({ result, sel, setSel }) {
  const attempts = result.attempts;
  const repo = result.repo;
  if (!attempts.length) {
    return (
      <EmptyState icon="flask" title="No tests were generated">
        {result.llm && !result.llm.configured ? "Test generation needs an LLM, and none is configured." : result.final.message}
      </EmptyState>
    );
  }
  const a = attempts[Math.min(sel, attempts.length - 1)];
  const v = a.validation;
  const hasTest = hasText(a.test_code);
  // One file per attempt; the attempt number is only added when there is more than one to tell apart.
  const testFile = attempts.length > 1 ? `generated_tests_attempt_${a.n}.py` : "generated_tests.py";
  return (
    <div className="stack">
      <AttemptPicker attempts={attempts} value={sel} onChange={setSel} />
      <div>
        <h3 className="sub">Test execution</h3>
        {!v ? (
          <Banner tone="warn" title="Tests were not executed">{a.apply_error ? "The patch could not be applied, so there was nothing to test." : "No validation result exists for this attempt."}</Banner>
        ) : v.verdict === "validated" ? (
          <Banner tone="success" title="Validated">{v.message}</Banner>
        ) : v.verdict === "not_validated" || v.verdict === "run_error" ? (
          <Banner tone="warn" title="Tests were not executed" actions={<a className="btn btn-secondary btn-sm" href="#/settings">Setup steps</a>}>
            {v.message} No pass/fail claims are made.
          </Banner>
        ) : (
          <Banner tone="danger" title="Did not pass validation">{v.message}</Banner>
        )}
        {v && (v.before || v.after) && (
          <div className="runs">
            <RunCard title="Before the fix" subtitle="Original code + generated test. The test should FAIL here." run={v.before} />
            <RunCard title="After the fix" subtitle="Patched code + generated test. The test should PASS here." run={v.after} />
          </div>
        )}
        {v && v.regressions && v.regressions.length > 0 && (
          <Banner tone="danger" title="Regressions">{v.regressions.join(", ")}</Banner>
        )}
        {repo && repo.test_targets.length > 0 && <p className="muted tiny">Existing repository tests included in each run: {repo.test_targets.join(", ")}</p>}
      </div>
      <div>
        <h3 className="sub">Generated test</h3>
        {a.test_rationale && <p>{a.test_rationale}</p>}
        {hasTest ? (
          <CodeBlock code={a.test_code} maxHeight={320} download={{ filename: testFile }} />
        ) : (
          <div className="inline-row">
            <p className="muted">No test code is available for this attempt.</p>
            <DownloadButton content="" filename={testFile} />
          </div>
        )}
        <p className="muted tiny">A useful test must fail on the original code. A test that already passes is reported as “not reproduced”, never as a fix.</p>
      </div>
    </div>
  );
}
