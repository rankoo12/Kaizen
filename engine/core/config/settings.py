from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # v2-style config (replaces old inner `class Config`)
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    OLLAMA_HOST: str = Field(default="http://localhost:11434")
    LLM_TEXT_MODEL: str = Field(default="llama3")
