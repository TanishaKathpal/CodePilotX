// Turns the real /api/health response into status indicators and setup guidance.
// Nothing here is invented: every value comes from `health` (or its absence).

export function deriveReadiness(health, offline) {
  const backend = offline
    ? { tone: "danger", value: "Offline", detail: "The frontend cannot reach the API. Start it with: uvicorn app.main:app --port 8000" }
    : health
      ? { tone: "success", value: "Connected", detail: "The API is responding." }
      : { tone: "neutral", value: "Checking", detail: "Contacting the backend…" };

  const unknown = (label) => ({ tone: "neutral", value: offline ? "Unknown" : "Checking", detail: `${label} status is unknown until the backend responds.` });
  let llm = unknown("LLM");
  let sandbox = unknown("Sandbox");
  let orchestrator = unknown("Orchestrator");
  let embeddings = unknown("Embedding");

  if (health) {
    llm = health.llm.configured
      ? { tone: "success", value: "Configured", detail: `${health.llm.provider} · ${health.llm.model}`,
          note: "A key was detected. It is only proven to work when an analysis runs." }
      : { tone: "warn", value: "Not configured", detail: "Analysis runs in retrieval-only mode: repository scan and code retrieval work, diagnosis and fixes need an LLM.",
          fix: {
            title: "Enable AI diagnosis",
            steps: [
              "Copy .env.example to .env in the project root.",
              "Set your key (copy the line below), or use LLM_PROVIDER=openai_compatible with OPENAI_API_KEY.",
              "Restart the backend so it reads the new environment.",
            ],
            snippet: "ANTHROPIC_API_KEY=your-key-here",
          } };
    sandbox = health.sandbox.available
      ? { tone: "success", value: "Ready", detail: `Docker image ${health.sandbox.image}` }
      : { tone: "warn", value: "Unavailable", detail: health.sandbox.detail,
          fix: {
            title: "Enable test execution",
            steps: [
              "Install and start Docker (Docker Desktop on Windows/macOS).",
              "Build the sandbox image (copy the command below).",
              "Return to this tab: status refreshes automatically.",
            ],
            snippet: "docker build -t codepilotx-sandbox sandbox/",
          } };
    orchestrator = { tone: "info", value: health.orchestrator === "langgraph" ? "LangGraph" : "Sequential",
      detail: health.orchestrator === "langgraph" ? "Agent steps run as a LangGraph state graph." : "Agent steps run in a plain loop (LangGraph not installed or disabled)." };
    embeddings = { tone: "info", value: health.embedding_backend, detail: health.embedding_backend === "hashing"
      ? "Offline lexical embeddings: matches shared words, not deep meaning." : "Neural embedding model." };
  }
  const caps = {
    scan: true,
    retrieve: true,
    diagnose: !!(health && health.llm.configured),
    validate: !!(health && health.llm.configured && health.sandbox.available),
  };
  return { backend, llm, sandbox, orchestrator, embeddings, caps };
}
