import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createJob, getHealth, getJob, getSamples } from "./api.js";
import Sidebar from "./components/Sidebar.jsx";
import Header from "./components/Header.jsx";
import OverviewView from "./views/OverviewView.jsx";
import AnalyzeView from "./views/AnalyzeView.jsx";
import HistoryView from "./views/HistoryView.jsx";
import SettingsView from "./views/SettingsView.jsx";
import { deriveReadiness } from "./lib/readiness.js";

const VIEWS = ["overview", "analyze", "history", "settings"];
const parseHash = () => {
  const v = window.location.hash.replace(/^#\/?/, "");
  return VIEWS.includes(v) ? v : "overview";
};

export default function App() {
  const [view, setView] = useState(parseHash());
  const [navOpen, setNavOpen] = useState(false);
  const [health, setHealth] = useState(null);
  const [offline, setOffline] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [samples, setSamples] = useState([]);
  const [samplesError, setSamplesError] = useState("");
  const [repo, setRepo] = useState("");
  const [issue, setIssue] = useState("");
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const timer = useRef(null);
  const runId = useRef(0);

  useEffect(() => {
    const onHash = () => { setView(parseHash()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const refreshHealth = useCallback(async () => {
    setRefreshing(true);
    try {
      setHealth(await getHealth());
      setOffline(false);
    } catch {
      setOffline(true);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    refreshHealth();
    getSamples().then(setSamples).catch((e) => setSamplesError(e.message));
    // Re-check when the user comes back to the tab (e.g. after building the sandbox image).
    const onVis = () => { if (document.visibilityState === "visible") refreshHealth(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { document.removeEventListener("visibilitychange", onVis); clearTimeout(timer.current); };
  }, [refreshHealth]);

  const poll = useCallback((id, gen) => {
    let failures = 0;
    const tick = async () => {
      try {
        const j = await getJob(id);
        if (gen !== runId.current) return; // a newer run replaced this one
        failures = 0;
        setJob(j);
        if (j.status === "queued" || j.status === "running") timer.current = setTimeout(tick, 1000);
      } catch (e) {
        if (gen !== runId.current) return;
        failures += 1;
        if (failures < 4) timer.current = setTimeout(tick, 1500);
        else setError(`Lost contact with the backend while waiting for results. ${e.message}`);
      }
    };
    tick();
  }, []);

  const start = useCallback(async (r, i) => {
    const gen = ++runId.current;
    clearTimeout(timer.current);
    setError("");
    setJob(null);
    setSubmitting(true);
    window.location.hash = "#/analyze";
    try {
      const { job_id } = await createJob(r, i); // unchanged payload: { repo_url, issue }
      if (gen !== runId.current) return;
      poll(job_id, gen);
    } catch (e) {
      if (gen === runId.current) setError(e.message);
    } finally {
      if (gen === runId.current) setSubmitting(false);
    }
  }, [poll]);

  const readiness = useMemo(() => deriveReadiness(health, offline), [health, offline]);
  const active = !!job && (job.status === "queued" || job.status === "running");
  const busy = submitting || active;
  const form = { repo, setRepo, issue, setIssue, samples, samplesError, onSubmit: start };

  return (
    <div className="shell">
      <Sidebar view={view} open={navOpen} onClose={() => setNavOpen(false)} />
      <div className="main">
        <Header view={view} readiness={readiness} job={job} onMenu={() => setNavOpen(true)} onRefresh={refreshHealth} refreshing={refreshing} />
        <main className="content" id="content">
          {view === "overview" && <OverviewView form={form} readiness={readiness} job={job} busy={busy} />}
          {view === "analyze" && <AnalyzeView form={form} readiness={readiness} job={job} busy={busy} error={error} onDismissError={() => setError("")} />}
          {view === "history" && <HistoryView job={job} />}
          {view === "settings" && <SettingsView health={health} readiness={readiness} offline={offline} />}
        </main>
      </div>
    </div>
  );
}
