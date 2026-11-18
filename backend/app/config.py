"""Central configuration. Everything comes from environment variables (see .env.example).

Secrets (API keys) are ONLY read from the environment -- never hard-code them.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
SAMPLES_DIR = PROJECT_DIR / "samples"


def _load_dotenv() -> None:
    """Load PROJECT_DIR/.env if python-dotenv is installed (it is in requirements.txt)."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - optional convenience
        return
    load_dotenv(PROJECT_DIR / ".env", override=False)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}")


def _float_or_none(name: str):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be a number, got {raw!r}")


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # --- LLM ---
    llm_provider: str = "anthropic"  # "anthropic" | "openai_compatible"
    llm_model: str = "claude-sonnet-5-5"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    llm_max_tokens: int = 4096
    llm_timeout_s: int = 120
    llm_temperature: float | None = None  # unset by default (some models restrict it)

    # --- Embeddings / retrieval ---
    embedding_backend: str = "hashing"  # "hashing" (offline) | "sentence-transformers"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    top_k: int = 8
    max_context_chars: int = 24000

    # --- Repository limits ---
    workspace_dir: Path = BACKEND_DIR / ".workspace"
    max_repo_mb: int = 50
    max_files_indexed: int = 1500
    max_file_kb: int = 200
    clone_timeout_s: int = 90

    # --- Sandbox ---
    sandbox_image: str = "codepilotx-sandbox:latest"
    sandbox_memory: str = "512m"
    sandbox_cpus: str = "1.0"
    sandbox_pids: int = 128
    sandbox_timeout_s: int = 120

    # --- Agent ---
    max_fix_attempts: int = 2
    use_langgraph: bool = True
    max_concurrent_jobs: int = 2
    keep_workspace: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()
        e = os.environ.get
        return cls(
            llm_provider=e("LLM_PROVIDER", "anthropic").strip().lower(),
            llm_model=e("LLM_MODEL", "claude-sonnet-5-5").strip(),
            anthropic_api_key=e("ANTHROPIC_API_KEY", "").strip(),
            anthropic_base_url=e("ANTHROPIC_BASE_URL", "https://api.anthropic.com").strip().rstrip("/"),
            openai_api_key=e("OPENAI_API_KEY", "").strip(),
            openai_base_url=e("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/"),
            llm_max_tokens=_int("LLM_MAX_TOKENS", 4096),
            llm_timeout_s=_int("LLM_TIMEOUT_S", 120),
            llm_temperature=_float_or_none("LLM_TEMPERATURE"),
            embedding_backend=e("EMBEDDING_BACKEND", "hashing").strip().lower(),
            embedding_model=e("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2").strip(),
            top_k=_int("TOP_K", 8),
            max_context_chars=_int("MAX_CONTEXT_CHARS", 24000),
            workspace_dir=Path(e("WORKSPACE_DIR", str(BACKEND_DIR / ".workspace"))),
            max_repo_mb=_int("MAX_REPO_MB", 50),
            max_files_indexed=_int("MAX_FILES_INDEXED", 1500),
            max_file_kb=_int("MAX_FILE_KB", 200),
            clone_timeout_s=_int("CLONE_TIMEOUT_S", 90),
            sandbox_image=e("SANDBOX_IMAGE", "codepilotx-sandbox:latest").strip(),
            sandbox_memory=e("SANDBOX_MEMORY", "512m").strip(),
            sandbox_cpus=e("SANDBOX_CPUS", "1.0").strip(),
            sandbox_pids=_int("SANDBOX_PIDS", 128),
            sandbox_timeout_s=_int("SANDBOX_TIMEOUT_S", 120),
            max_fix_attempts=max(1, _int("MAX_FIX_ATTEMPTS", 2)),
            use_langgraph=_bool("USE_LANGGRAPH", True),
            max_concurrent_jobs=max(1, _int("MAX_CONCURRENT_JOBS", 2)),
            keep_workspace=_bool("KEEP_WORKSPACE", False),
            cors_origins=e("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"),
        )

    @property
    def llm_api_key(self) -> str:
        return self.anthropic_api_key if self.llm_provider == "anthropic" else self.openai_api_key
