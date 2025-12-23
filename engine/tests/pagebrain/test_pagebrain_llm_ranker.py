from __future__ import annotations

from typing import Any, Dict, List

from engine.core.pagebrain.llm_ranker import (
    LlmRankerResult,
    QwenLlmPageBrainRanker,
)


def _fake_response_ok() -> Dict[str, Any]:
    """Minimal OpenAI-like response object for a successful ARQ call."""

    content = (
        '{'
        '"ranking": [1, 0],'
        '"scores": {"0": 0.2, "1": 0.9},'
        '"verification": {"violated_constraints": false, "guessed_fields": false},'
        '"needs_more_data": false'
        '}'
    )
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                }
            }
        ]
    }


def _fake_response_needs_more() -> Dict[str, Any]:
    content = (
        '{'
        '"ranking": [0],'
        '"scores": {"0": 0.5},'
        '"verification": {"violated_constraints": false, "guessed_fields": false},'
        '"needs_more_data": true'
        '}'
    )
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                }
            }
        ]
    }


def _make_ranker(monkeypatch, response: Dict[str, Any]) -> QwenLlmPageBrainRanker:
    ranker = QwenLlmPageBrainRanker(
        base_url="http://test-llm.local",
        model="qwen2.5-vl-72b-instruct",
        timeout_seconds=1.0,
    )

    def _fake_call_model(payload: Dict[str, Any]) -> Dict[str, Any] | None:  # noqa: ARG001
        return response

    monkeypatch.setattr(ranker, "_call_model", _fake_call_model)
    return ranker


def test_qwen_ranker_happy_path(monkeypatch):
    ranker = _make_ranker(monkeypatch, _fake_response_ok())
    target: Dict[str, Any] = {"text": "click login"}
    candidates: List[Dict[str, Any]] = [
        {"type": "css", "value": "#a", "visible": True, "enabled": True},
        {"type": "css", "value": "#b", "visible": True, "enabled": True},
    ]

    result = ranker.rank(target=target, candidates=candidates, dom_context=None, perception=None)
    assert isinstance(result, LlmRankerResult)
    # Ranking should be taken from the JSON payload
    assert result.ranking == [1, 0]
    # Scores should be normalized and keyed by int indices
    assert result.scores.get(1) == 0.9
    assert result.raw.get("model_id") == "qwen2.5-vl-72b-instruct"


def test_qwen_ranker_rejects_needs_more_data(monkeypatch):
    ranker = _make_ranker(monkeypatch, _fake_response_needs_more())
    target: Dict[str, Any] = {"text": "click login"}
    candidates: List[Dict[str, Any]] = [
        {"type": "css", "value": "#a", "visible": True, "enabled": True},
    ]

    result = ranker.rank(target=target, candidates=candidates, dom_context=None, perception=None)
    # Because needs_more_data=true, the ranker should signal failure so that
    # PageBrainFinder can fall back to the deterministic ranker.
    assert result is None
