from pydantic import BaseSettings


class Settings(BaseSettings):
    OLLAMA_HOST: str = "http://localhost:11434"
    KAIZEN_DB: str = "/data/kaizen.sqlite"
    LLM_TEXT_MODEL: str = "llama3:8b"
    LLM_VISION_MODEL: str | None = None

    class Config:
        env_file = ".env"
