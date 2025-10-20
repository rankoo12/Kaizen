# engine/core/config/settings.py
from pathlib import Path
from typing import Literal
from pydantic import Field, ConfigDict
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
        default="legacy", description="Selects live execution path"
    )
    model_config = ConfigDict(env_prefix="KAIZEN_")


settings = Settings()

# Ensure folders exist (small DX improvement, non-fatal)
settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
settings.SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


# Shared settings getter for DI
def get_settings() -> Settings:
    return settings
