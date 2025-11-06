# engine/core/config/settings.py
from pathlib import Path
from typing import Literal, List
from pydantic import Field, ConfigDict, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Snapshot MVP tolerances (env-overridable)
    VISUAL_TOLERANCE: float = Field(
        0.0025, description="Allowed visual diff ratio (0.25%)"
    )
    HEALER_DEPTH: int = Field(2, description="Max attempts for simple selector healing")

    # Paths
    LOGS_DIR: Path = Field(default=Path("logs"))
    SNAPSHOTS_DIR: Path = Field(default=Path("snapshots"))

    # Metadata
    VERSION: str = "0.0.0-dev"
    GIT_SHA: str = "dev"

    # Logging
    LOG_MAX_BYTES: int = Field(
        5_000_000, description="Max size per JSONL log before rotation (bytes)"
    )

    # Execution toggle for LiveRunner delegation
    EXECUTION_PATH: Literal["legacy", "orchestrator"] = Field(
        default="orchestrator", description="Selects live execution path"
    )

    # Planner path: glue (rule-based) or llm (ILLMText)
    PLANNER_PATH: Literal["glue", "llm"] = Field(default="glue")

    # Security: allowed URL schemes for live open()
    ALLOWED_URL_SCHEMES: List[str] | str = Field(
        default_factory=lambda: ["data:", "about:blank"],
        description="Whitelisted URL schemes or exact values allowed for open()",
    )

    # Healing toggle (deterministic heuristics only)
    HEALER_ENABLED: bool = Field(default=False, description="Enable deterministic selector healing")

    # Healer path: deterministic heuristics or llm proposals
    HEALER_PATH: Literal["deterministic", "llm"] = Field(default="deterministic")

    # Optional per-step enrichment in logs
    REPORT_STEP_HEAL_FLAGS: bool = Field(default=False)

    # Default executor timeout for resolve polling (ms). If None, legacy
    # immediate behavior applies unless a per-step ctx.timeout_ms is given.
    EXEC_TIMEOUT_MS: int | None = Field(default=None)

    # Optional hard caps (ms)
    RUN_TIMEOUT_MS: int | None = Field(default=None, description="Abort a run after this many milliseconds")
    EXEC_STEP_TIMEOUT_MS: int | None = Field(default=None, description="Per-step soft timeout (currently applied to resolve phase only)")

    # SBOM reference identifier (if available) to tag run logs/metrics
    SBOM_REF: str | None = Field(default=None)

    # Reporter backend: in-memory or JSONL tailer
    REPORTER_BACKEND: Literal["in_memory", "jsonl_tail"] = Field(default="in_memory")
    REPORTER_RESYNC_ON_START: bool = Field(default=False)

    # Storage (Postgres)
    PG_DSN: str | None = Field(default=None, description="Postgres DSN, e.g. postgresql+psycopg://user:pass@host:5432/db")
    STORAGE_BACKEND: Literal["auto", "in_memory", "postgres"] = Field(default="auto")

    # LLM planner (disabled by default)
    LLM_ENABLED: bool = Field(default=False, description="Enable LLM planner/preview endpoints")
    OLLAMA_BASE_URL: str = Field(default="http://ollama:11434", description="Ollama base URL")
    OLLAMA_MODEL: str = Field(default="llama3.1", description="Ollama model name")
    LLM_TIMEOUT_SECONDS: float = Field(default=10.0, description="Timeout for LLM calls (seconds)")
    LLM_MAX_TOKENS: int = Field(default=256, description="Max tokens to generate for LLM responses")
    LLM_TEMPERATURE: float = Field(default=0.2, description="LLM sampling temperature (0..1)")

    # Planner preview guardrails (rate limit + input caps)
    PREVIEW_RATE_WINDOW_SEC: int = Field(
        default=60, description="Rate limit window size in seconds for /api/plan/preview"
    )
    PREVIEW_RATE_MAX_REQUESTS: int = Field(
        default=30, description="Max requests per window per key for /api/plan/preview"
    )
    PREVIEW_INPUT_TEXT_MAX_CHARS: int = Field(
        default=500, description="Max characters allowed in 'text' for plan preview"
    )
    PREVIEW_CONTEXT_HTML_MAX_CHARS: int = Field(
        default=4000, description="Max characters of HTML context allowed in plan preview"
    )

    # Multitenancy and admin
    MULTITENANT_ENFORCED: bool = Field(
        default=False,
        description="Require API key and enforce tenant isolation on queue/state APIs",
    )
    ADMIN_SECRET: str | None = Field(
        default=None, description="Shared secret for admin endpoints via X-Admin-Secret header"
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_allowed_schemes(cls, data):
        try:
            raw = data.get("ALLOWED_URL_SCHEMES") if isinstance(data, dict) else None
        except Exception:
            raw = None
        if isinstance(raw, str):
            parts = [p.strip() for p in raw.split(",")]
            data["ALLOWED_URL_SCHEMES"] = [p for p in parts if p]
        # If a single string sneaks through, normalize to a one-item list
        if isinstance(data.get("ALLOWED_URL_SCHEMES"), str):
            s = data["ALLOWED_URL_SCHEMES"].strip()
            data["ALLOWED_URL_SCHEMES"] = [s] if s else []
        return data
    model_config = ConfigDict(env_prefix="KAIZEN_")


settings = Settings()

# Ensure folders exist (small DX improvement, non-fatal)
settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
settings.SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


# Shared settings getter for DI
def get_settings() -> Settings:
    return settings
