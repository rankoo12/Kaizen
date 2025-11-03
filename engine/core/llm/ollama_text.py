from __future__ import annotations

import httpx

from .text_llm import ILLMText


class OllamaTextAdapter(ILLMText):
    """Ollama text adapter with endpoint fallback (/api/generate -> /api/chat).

    Allows basic generation controls via max_tokens and temperature to keep
    responses short and deterministic for planning.
    """

    def __init__(self, base_url: str, model: str, timeout: float = 10.0, *, max_tokens: int = 256, temperature: float = 0.2) -> None:
        base = (base_url or "").rstrip("/")
        # Normalize accidental '/api' suffix to avoid '/api/api/*'
        if base.endswith("/api"):
            base = base[:-4]
        self._base = base
        self._model = model
        self._timeout = timeout
        self._max_tokens = int(max_tokens) if max_tokens is not None else 256
        try:
            self._temperature = float(temperature)
        except Exception:
            self._temperature = 0.2

    def ask(self, prompt: str) -> str:
        generate_url = f"{self._base}/api/generate"
        chat_url = f"{self._base}/api/chat"
        gen_payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": self._temperature, "num_predict": self._max_tokens},
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                # Try /api/generate first
                try:
                    r = client.post(generate_url, json=gen_payload)
                    r.raise_for_status()
                    data = r.json()
                    text = data.get("response") if isinstance(data, dict) else None
                    # If empty/invalid content, fall back to chat endpoint
                    if not text or not isinstance(text, str) or not text.strip():
                        raise httpx.HTTPStatusError("empty generate response", request=r.request, response=r)
                    return str(text)
                except httpx.HTTPStatusError as se:
                    # Fallback to /api/chat on 404/405 or obvious endpoint errors
                    code = getattr(se.response, "status_code", None)
                    if code not in (404, 405, 200):
                        raise
                except httpx.RequestError:
                    # Connection errors will bubble after chat attempt
                    pass

                # Fallback: /api/chat
                chat_payload = {
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": self._temperature, "num_predict": self._max_tokens},
                }
                rc = client.post(chat_url, json=chat_payload)
                rc.raise_for_status()
                data = rc.json()
                # Chat response structure: { message: { content: "..." }, ... }
                text = None
                if isinstance(data, dict):
                    msg = data.get("message") or {}
                    if isinstance(msg, dict):
                        text = msg.get("content")
                if not text:
                    text = rc.text
                return str(text)
        except Exception as e:
            raise RuntimeError(f"ollama request failed: {e}")
