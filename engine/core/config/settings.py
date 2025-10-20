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

    # Security: allowed URL schemes for live open()
    ALLOWED_URL_SCHEMES: List[str] | str = Field(
        default_factory=lambda: ["data:", "about:blank"],
        description="Whitelisted URL schemes or exact values allowed for open()",
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
