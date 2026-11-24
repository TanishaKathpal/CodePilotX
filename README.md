# CodePilotX

**An Agentic AI Platform for Repository-Level Code Intelligence, Debugging, and Automated Testing**

CodePilotX is an AI-powered debugging platform that analyzes GitHub repositories, identifies potential bugs, proposes code fixes, generates tests, and validates fixes in an isolated Docker sandbox.

Users provide a public GitHub repository and describe an issue. CodePilotX analyzes the repository, retrieves relevant code, uses an LLM to diagnose the issue, and proposes a patch with a corresponding test.

> **Core principle:** CodePilotX only reports a fix as validated when the generated test fails on the original code and passes on the patched code without regressions. Otherwise, the fix is explicitly marked as **NOT VALIDATED**.

## Key Features

- **Repository Analysis:** Loads and analyzes public GitHub repositories.
- **AST-Based Code Analysis:** Extracts Python functions and classes using Abstract Syntax Trees.
- **RAG-Based Retrieval:** Retrieves relevant code snippets using embeddings and vector similarity.
- **AI-Powered Diagnosis:** Uses an LLM to identify potential root causes.
- **Automated Fix Generation:** Generates search-and-replace patches and corresponding pytest tests.
- **Iterative Agent Workflow:** Uses LangGraph to coordinate analysis, diagnosis, patching, and retry steps.
- **Sandbox-Based Validation:** Executes tests inside an isolated Docker environment.
- **Honest Validation:** Distinguishes validated fixes from suggested but unverified fixes.

## Architecture

```text
             React Frontend
                   |
                FastAPI
                   |
             Background Job
                   |
             Agent Workflow
                   |
       +-----------+-----------+
       |           |           |
   Load Repo  Analyze Repo  Index Repo
       |           |           |
       +-----------+-----------+
                   |
               Retrieval
                   |
               Diagnosis
                   |
              Propose Fix
                   |
              Apply Patch
                   |
           Docker Validation
                   |
           Before/After Tests
                   |
              Final Result
```

### Workflow

1. **Load Repository:** Safely clones the selected repository.
2. **Analyze Repository:** Extracts files, functions, classes, and code structure.
3. **Index Repository:** Creates embeddings and stores code chunks.
4. **Retrieve Context:** Finds relevant code based on the issue description.
5. **Diagnose Issue:** Uses the LLM to identify the likely root cause.
6. **Propose Fix:** Generates a patch and a pytest test.
7. **Apply Patch:** Applies edits to a separate repository copy.
8. **Validate Fix:** Runs tests against original and patched code in Docker.

## Technology Stack

| Component | Technologies |
|---|---|
| Frontend | React, Vite |
| Backend | Python, FastAPI |
| AI Integration | Groq API (OpenAI-compatible endpoint) |
| LLM Model | openai/gpt-oss-120b |
| Agent Orchestration | LangGraph |
| Retrieval | RAG, Hashing Embeddings, NumPy |
| Code Analysis | Python AST |
| Testing | Pytest |
| Sandbox | Docker |
| Version Control | Git, GitHub |

## Project Structure

```text
codepilotx/
│
├── backend/
│   ├── app/
│   │   ├── repo/
│   │   ├── rag/
│   │   ├── llm/
│   │   ├── config.py
│   │   ├── workflow.py
│   │   ├── sandbox.py
│   │   ├── patching.py
│   │   ├── validation.py
│   │   ├── service.py
│   │   └── main.py
│   │
│   └── tests/
│
├── frontend/
│   ├── src/
│   └── package.json
│
├── sandbox/
│   └── Dockerfile
│
├── samples/
│   └── tasks.json
│
├── evaluation/
│   └── run_eval.py
│
├── .env.example
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+ (20+ recommended)
- npm
- Git
- Docker Desktop (required for sandbox test execution)
- Groq API key

### 1. Clone the Repository

```bash
git clone https://github.com/TanishaKathpal/CodePilotX.git
cd CodePilotX
```

### 2. Configure Environment Variables

Create a `.env` file in the project root using `.env.example` as a reference.

For Groq through an OpenAI-compatible endpoint:

```env
LLM_PROVIDER=openai_compatible
LLM_MODEL=openai/gpt-oss-120b
OPENAI_API_KEY=YOUR_GROQ_API_KEY
OPENAI_BASE_URL=https://api.groq.com/openai/v1
EMBEDDING_BACKEND=hashing
USE_LANGGRAPH=true
```

Replace `YOUR_GROQ_API_KEY` with your Groq API key.

**Important:** Never commit your `.env` file or expose API keys publicly.

### 3. Set Up the Backend

```bash
cd backend

python -m venv .venv
```

Activate the environment:

**Windows PowerShell:**

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the backend:

```bash
python -m uvicorn app.main:app --port 8000
```

Backend API: `http://localhost:8000`

API documentation: `http://localhost:8000/docs`

### 4. Set Up the Frontend

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`

### 5. Build the Sandbox Image

Docker is required for actual automated test validation.

```bash
docker build -t codepilotx-sandbox sandbox/
```

If Docker is unavailable, CodePilotX must not claim that a fix has been validated.

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Checks backend, LLM, and sandbox status |
| GET | `/api/samples` | Lists bundled sample tasks |
| POST | `/api/jobs` | Starts a repository analysis |
| GET | `/api/jobs/{id}` | Retrieves job progress and results |

## Security Considerations

Repository contents are treated as untrusted input.

CodePilotX incorporates security measures such as:

- GitHub HTTPS URL allow-listing.
- Repository size and file-count limits.
- Safe Git clone configuration.
- Removal of Git metadata and symlinks.
- No execution of repository code on the host machine.
- Docker sandbox restrictions, including disabled networking, resource limits, dropped capabilities, and a read-only root filesystem.
- Validation of generated patches and protection of test files.
- Prompt-injection mitigation for repository content.
- Secret handling through environment variables.

**Note:** Container isolation reduces execution risk but is not a perfect security boundary. The application should not be exposed publicly without additional authentication, rate limiting, and security hardening.

## Testing and Verification

The backend automated test suite was executed locally.

| Test Result | Status |
|---|---:|
| Passed | 130 |
| Skipped | 3 |
| Failed | 0 |
| Additional subtests | 12 passed |

### End-to-End Verification

CodePilotX was successfully tested with a sample banking repository and a withdrawal-related bug.

The generated fix addressed the issue where withdrawing an amount exactly equal to the account balance incorrectly raised an `InsufficientFunds` exception.

| Workflow Stage | Result |
|---|---|
| Repository Scan | Complete |
| Code Retrieval | Complete |
| Issue Diagnosis | Complete |
| Fix Generation | Complete |
| Docker Test Validation | Complete |

**Validation results:**
- Generated test failed before the fix.
- Generated test passed after the fix.
- All 4 existing tests that passed before the change continued to pass.
- One file was modified by the generated patch.
- End-to-end pipeline completed in approximately 17 seconds.

The Docker sandbox image was also built and its Python/pytest execution smoke-tested successfully.

These results demonstrate successful validation on the tested sample repository; they do not guarantee correctness for every repository or issue.

## Sample Tasks and Evaluation

The `samples/` directory contains five small Python repositories with planted bugs and reference fixes.

Run retrieval evaluation:

```bash
python evaluation/run_eval.py
```

Run oracle evaluation (requires Docker):

```bash
python evaluation/run_eval.py --mode oracle
```

Run full evaluation (requires an LLM API key and Docker):

```bash
python evaluation/run_eval.py --mode full
```

## Scope and Limitations

- Python receives AST-based function and class chunking. Other text files use window-based chunking.
- Automated test execution currently supports Python and pytest.
- The default hashing-based embedding approach is lexical rather than fully semantic.
- Repository size and file-count limits apply.
- The sandbox does not have network access.
- Tests requiring external services, databases, or unsupported dependencies may not run.
- Jobs are maintained in memory and are lost when the backend restarts.
- AI-generated fixes still require human review.

## Future Enhancements

- Support for JavaScript and TypeScript test execution.
- Persistent job storage and analysis history.
- Server-Sent Events for real-time progress updates.
- Advanced vector databases such as FAISS or ChromaDB.
- Improved semantic embeddings.
- Authentication and API rate limiting.
- Stronger sandbox isolation for untrusted workloads.

---

**CodePilotX — Making AI-assisted debugging more structured, explainable, and test-driven.**

**Developed by Tanisha Kathpal**
