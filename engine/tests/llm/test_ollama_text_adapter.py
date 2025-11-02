from __future__ import annotations

import types
import httpx

from engine.core.llm.ollama_text import OllamaTextAdapter


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload

    @property
    def text(self):
        return str(self._payload)


class _ClientCtx:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json):
        return _Resp(self._payload)


def test_ollama_adapter_parses_response(monkeypatch):
    def _fake_client(*a, **k):
        return _ClientCtx({"response": "hello"})

    monkeypatch.setattr(httpx, "Client", _fake_client)
    ad = OllamaTextAdapter("http://ollama:11434", "llama3")
    out = ad.ask("hi")
    assert out == "hello"


def test_ollama_adapter_raises_on_error(monkeypatch):
    class _BadClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            raise httpx.RequestError("boom")

    monkeypatch.setattr(httpx, "Client", _BadClient)
    ad = OllamaTextAdapter("http://ollama:11434", "llama3")
    try:
        ad.ask("hi")
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "ollama request failed" in str(e)
