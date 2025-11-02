from __future__ import annotations

import httpx

from .text_llm import ILLMText


class OllamaTextAdapter(ILLMText):
    """Minimal Ollama text adapter using /api/generate (no streaming)."""

    def __init__(self, base_url: str, model: str, timeout: float = 10.0) -> None:
        self._base = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def ask(self, prompt: str) -> str:
        url = f"{self._base}/api/generate"
        payload = {"model": self._model, "prompt": prompt, "stream": False}
        try:
            with httpx.Client(timeout=self._timeout) as client:
                r = client.post(url, json=payload)
                r.raise_for_status()
                data = r.json()
                # Non-stream response uses 'response'
                text = data.get("response") if isinstance(data, dict) else None
                if not text:
                    # Fallback to raw text
                    text = r.text
                return str(text)
        except Exception as e:
            raise RuntimeError(f"ollama request failed: {e}")
