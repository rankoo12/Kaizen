# engine/core/config/settings.py
from pathlib import Path
from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Snapshot MVP tolerances (env-overridable)
    VISUAL_TOLERANCE: float = Field(
        0.0025, description="Allowed visual diff ratio (0.25%)"
    )
    HEALER_DEPTH: int = Field(2, description="Max attempts for simple selector healing")

    # Paths
    LOGS_DIR: Path = Field(default=Path("logs"))
    SNAPSHOTS_DIR: Path = Field(default=Path("snapshots"))

    model_config = ConfigDict(env_prefix="KAIZEN_")


settings = Settings()

# Ensure folders exist (small DX improvement, non-fatal)
settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
settings.SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
