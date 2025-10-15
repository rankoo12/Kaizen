from typing import Protocol


class ILLMText(Protocol):
    """Local LLM text interface (Ollama adapter later)."""

    def ask(self, prompt: str) -> str: ...
