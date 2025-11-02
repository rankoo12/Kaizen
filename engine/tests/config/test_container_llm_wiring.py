from __future__ import annotations

from engine.core.config.container import Container
from engine.core.llm.ollama_text import OllamaTextAdapter


class _S:
    def __init__(self, enabled: bool):
        self.LLM_ENABLED = enabled
        self.OLLAMA_BASE_URL = "http://ollama:11434"
        self.OLLAMA_MODEL = "llama3"
        self.LLM_TIMEOUT_SECONDS = 1.0


def test_llm_provider_disabled_returns_none():
    c = Container()
    c.settings.override(_S(False))
    assert c.llm_text() is None


def test_llm_provider_enabled_returns_adapter():
    c = Container()
    c.settings.override(_S(True))
    llm = c.llm_text()
    assert isinstance(llm, OllamaTextAdapter)
    assert hasattr(llm, "ask")
