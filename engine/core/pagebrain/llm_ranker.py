from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol
import logging


@dataclass
class LlmRankerResult:
    """Normalized result from the LLM ranker.

    The indices are positions into the original candidates list provided to the ranker.
    """

    ranking: List[int]
    scores: Dict[int, float]
    raw: Dict[str, Any]


_log = logging.getLogger(__name__)


class ILlmPageBrainRanker(Protocol):
    """Interface for PageBrain LLM rankers.

    Implementations are responsible for:
    - Building the ARQ prompt from target/candidates/context.
    - Calling the underlying model (e.g. local Qwen2.5-VL-72B).
    - Validating and normalizing the JSON output.

    They must not mutate the candidates; only return a ranking over indices.
    """

    def rank(
        self,
        *,
        target: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        dom_context: Dict[str, Any] | None = None,
        perception: Dict[str, Any] | None = None,
    ) -> LlmRankerResult | None:
        ...


class NoopLlmPageBrainRanker:
    """Fallback implementation used when no real LLM ranker is configured.

    This is primarily for wiring tests and environments where PAGEBRAIN_RANKER_MODE
    is set to "fallback". It always returns None so PageBrainFinder will use its
    GBM/tabular ranker.
    """

    def rank(
        self,
        *,
        target: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        dom_context: Dict[str, Any] | None = None,
        perception: Dict[str, Any] | None = None,
    ) -> LlmRankerResult | None:
        return None


class QwenLlmPageBrainRanker:
    """LLM ranker implementation backed by a local Qwen HTTP service.

    This class is intentionally conservative:
    - It assumes an OpenAI-like /v1/chat/completions API but does not depend on
      any external SDKs (uses urllib + json only).
    - It enforces JSON-only output and performs lightweight validation of the
      ARQ-shaped response before returning a ranking.
    - On any error or schema violation it returns None so the caller can fall
      back to the GBM/tabular ranker.
    """

    def __init__(self, *, base_url: str, model: str, timeout_seconds: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = float(timeout_seconds)
        # Optional extras used by subclasses/backends (e.g. OpenAI).
        # For local Qwen/vLLM these remain empty/None so that requests are
        # unauthenticated and use the minimal payload shape.
        self._headers: Dict[str, str] = {}
        self._response_format: Dict[str, Any] | None = None
        # Default decoding parameters; subclasses may override for specific
        # backends (e.g. some OpenAI models do not allow temperature!=1.0).
        self._temperature: float = 0.0
        # Name of the field used to cap generated tokens. Local vLLM/Qwen
        # typically expects ``max_tokens`` whereas newer OpenAI chat models
        # require ``max_completion_tokens``.
        self._max_tokens_field: str = "max_tokens"
        # Optional extra top-level parameters for specific backends
        # (e.g. reasoning_effort / verbosity for GPT‑5).
        self._extra_params: Dict[str, Any] = {}

    def rank(
        self,
        *,
        target: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        dom_context: Dict[str, Any] | None = None,
        perception: Dict[str, Any] | None = None,
    ) -> LlmRankerResult | None:
        if not candidates:
            return None
        try:
            prompt = self._build_prompt(target=target, candidates=candidates, dom_context=dom_context)
            payload = {
                "model": self._model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are Kaizen's PageBrain Finder LLM ranker. "
                            "Your job is to choose which DOM candidate best matches the target action. "
                            "You MUST respond with JSON only, following the requested schema. "
                            "Never invent new selectors; only reason over the provided candidates."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                # Deterministic decoding so that behaviour is inspectable and
                # stable across runs, assuming the underlying service honours
                # these parameters.
                "temperature": getattr(self, "_temperature", 0.0),
                # vLLM's OpenAI-compatible API requires 0 < top_p <= 1.0;
                # use 1.0 so sampling is effectively disabled when
                # temperature is 0.0, while still passing validation.
                "top_p": 1.0,
            }
            # Token cap field differs between backends: local vLLM expects
            # ``max_tokens`` while newer OpenAI chat models use
            # ``max_completion_tokens``.
            try:
                max_field = getattr(self, "_max_tokens_field", "max_tokens")
            except Exception:
                max_field = "max_tokens"
            payload[max_field] = 512
            # Backend-specific extra parameters (e.g. reasoning_effort).
            try:
                extra = getattr(self, "_extra_params", None)
                if isinstance(extra, dict):
                    for k, v in extra.items():
                        if k not in payload:
                            payload[k] = v
            except Exception:
                pass
            # Lightweight logging of the outbound request shape (without headers)
            # so that operators can debug issues. We avoid logging the full,
            # potentially large prompt by truncating the user message content.
            try:
                log_payload = dict(payload)
                msgs = list(log_payload.get("messages") or [])
                if len(msgs) > 1:
                    user_msg = dict(msgs[1] or {})
                    content = user_msg.get("content")
                    if isinstance(content, str) and len(content) > 512:
                        user_msg["content"] = content[:512] + "...[truncated]"
                    msgs[1] = user_msg
                    log_payload["messages"] = msgs
                _log.warning(
                    "pagebrain.llm_ranker.request model=%s keys=%s payload_preview=%s",
                    self._model,
                    list(log_payload.keys()),
                    {
                        "system": msgs[0] if msgs else None,
                        "user": msgs[1] if len(msgs) > 1 else None,
                        "temperature": log_payload.get("temperature"),
                        "top_p": log_payload.get("top_p"),
                    },
                )
            except Exception:
                pass
            # Allow backends (e.g. OpenAI) to opt-in to structured JSON
            # enforcement when supported. For local vLLM/Qwen this is left
            # unset to avoid 400s on older versions.
            if getattr(self, "_response_format", None):
                payload["response_format"] = self._response_format  # type: ignore[assignment]
            raw_response = self._call_model(payload)
            if not raw_response:
                return None
            content = self._extract_content(raw_response)
            if not isinstance(content, str) or not content.strip():
                # Log additional shape information so we can debug why the
                # content is empty without dumping the full payload.
                try:
                    keys = list(raw_response.keys()) if isinstance(raw_response, dict) else None
                    first_choice_summary = None
                    if isinstance(raw_response, dict):
                        ch = raw_response.get("choices")
                        if isinstance(ch, list) and ch:
                            c0 = ch[0] or {}
                            msg = c0.get("message") or {}
                            first_choice_summary = {
                                "finish_reason": c0.get("finish_reason"),
                                "index": c0.get("index"),
                                "message_keys": list(msg.keys()) if isinstance(msg, dict) else None,
                                "content_type": type(msg.get("content")).__name__ if isinstance(msg, dict) else None,
                            }
                    _log.warning(
                        "pagebrain.llm_ranker.empty_content keys=%s first_choice=%s",
                        keys,
                        first_choice_summary,
                    )
                except Exception:
                    pass
                return None

            import json

            # Strict mode: assume the content is JSON. If parsing fails, attempt
            # to recover the first [...] or {...} block; otherwise treat as failure.
            try:
                result_obj: Dict[str, Any] = json.loads(content)
            except Exception:
                start = min(
                    (i for i in (content.find("{"), content.find("[")) if i >= 0),
                    default=-1,
                )
                end = max(content.rfind("}"), content.rfind("]"))
                if start >= 0 and end > start:
                    try:
                        result_obj = json.loads(content[start : end + 1])
                    except Exception:
                        return None
                else:
                    return None

            # Attach token usage from the HTTP response when available so that callers
            # (PageBrainFinder, reporters, portal) can surface per-step and per-run
            # token statistics without needing to inspect the raw response.
            try:
                usage = raw_response.get("usage") if isinstance(raw_response, dict) else None
                if isinstance(usage, dict) and "usage" not in result_obj:
                    result_obj["usage"] = usage
            except Exception:
                pass

            ranking = self._validate_and_extract_ranking(result_obj, len(candidates))
            if not ranking:
                try:
                    _log.warning("pagebrain.llm_ranker.empty_ranking")
                except Exception:
                    pass
                return None
            scores = self._normalize_scores(result_obj.get("scores"), len(candidates))

            verification = result_obj.get("verification") or {}
            needs_more_data = bool(result_obj.get("needs_more_data", False))
            violated = bool(verification.get("violated_constraints"))
            guessed = bool(verification.get("guessed_fields"))
            # Decide how the caller should treat this result.
            # - needs_more_data=True  -> the model says the candidate set is insufficient.
            # - violated_constraints  -> the model believes hard rules were broken.
            # - guessed_fields        -> the model had to guess some required fields.
            #
            # We always return a ranking when available so that callers can
            # log and analyse it, but we tag the decision so that the Finder
            # can choose whether to *use* the ranking or fall back to the
            # deterministic ranker.
            if needs_more_data:
                llm_decision = "discarded_needs_more_data"
            elif violated:
                llm_decision = "discarded_violated"
            elif guessed:
                llm_decision = "used_with_guess"
            else:
                llm_decision = "used"

            if needs_more_data or violated:
                # Keep a warning log so operators understand why the Finder
                # may have fallen back even though the LLM was called.
                try:
                    _log.warning(
                        "pagebrain.llm_ranker.discarded needs_more_data=%s violated=%s guessed=%s",
                        needs_more_data,
                        violated,
                        guessed,
                    )
                except Exception:
                    pass

            # Attach model_id so callers can log it.
            if "model_id" not in result_obj:
                result_obj["model_id"] = self._model
            # Expose our interpretation of the ARQ verification flags so that
            # the Finder can record whether the LLM decision was used, skipped
            # due to uncertainty, or relied on despite guesses.
            result_obj.setdefault("llm_decision", llm_decision)

            return LlmRankerResult(ranking=ranking, scores=scores, raw=result_obj)
        except Exception as e:
            try:
                _log.warning(
                    "pagebrain.llm_ranker.exception error=%s",
                    type(e).__name__,
                )
            except Exception:
                pass
            return None

    # ---- internals ---------------------------------------------------------

    def _build_prompt(
        self,
        *,
        target: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        dom_context: Dict[str, Any] | None = None,
    ) -> str:
        """Build an ARQ-style text prompt summarizing target and candidates."""

        import json

        tool = (dom_context or {}).get("tool")
        domain = (dom_context or {}).get("domain")
        target_text = ""
        # Prefer the original step text (if supplied) as a richer
        # description of the intent; fall back to target["text"].
        try:
            step_text = target.get("__step_text")
            if isinstance(step_text, str) and step_text.strip():
                target_text = step_text.strip()
            else:
                t_text = target.get("text")
                if isinstance(t_text, str):
                    target_text = t_text
        except Exception:
            target_text = ""

        header_lines = [
            "You are given:",
            "- A target action (tool + description).",
            "- A list of DOM candidates. Each candidate has an index and a selector plus attributes.",
            "",
            "Your job:",
            "- Choose which candidate best matches the target.",
            "- Produce a JSON object with fields:",
            "  - restate_task: {tool, intent}",
            "  - hard_constraints: {must_be_visible, must_be_enabled, must_be_unique}",
            "  - candidate_elimination: [{index, reason}]",
            "  - ranking: [indices best_to_worst]",
            "  - scores: {index: float}",
            "  - top1_justification: {...}",
            "  - verification: {violated_constraints: bool, guessed_fields: bool}",
            "  - needs_more_data: bool",
            "",
            "Rules:",
            "- Only rank the provided candidates; do NOT invent new selectors.",
            "- Use the tool to decide which kinds of elements are valid:",
            "  - If tool == 'type': the correct candidate must be a text-entry field ",
            "    (tag in ['input','textarea'] or role in ['textbox','searchbox','combobox']).",
            "    Prefer these over buttons, links, or icon-only elements.",
            "  - If tool == 'click': the correct candidate should be a clickable control ",
            "    (tag in ['button','a'] or role in ['button','link','menuitem','tab']).",
            "    Avoid plain text fields for click unless there is no other plausible match.",
            "- If you are not confident you have enough information, set needs_more_data = true.",
            "- Respond with JSON only. Do NOT include any extra text before or after the JSON.",
        ]

        target_block = {
            "tool": tool,
            "domain": domain,
            "target": target,
            "target_text": target_text,
        }

        norm_candidates: List[Dict[str, Any]] = []
        for idx, c in enumerate(candidates):
            try:
                selector = {"type": c.get("type"), "value": c.get("value")}
                norm_candidates.append(
                    {
                        "index": idx,
                        "selector": selector,
                        "tag": c.get("tag"),
                        "role": c.get("role"),
                        "type": c.get("type"),
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "testid": c.get("testid"),
                        "aria_label": c.get("aria_label") or c.get("aria-label"),
                        "placeholder": c.get("placeholder"),
                        "text": c.get("text"),
                        "visible": c.get("visible", True),
                        "enabled": c.get("enabled", True),
                        "source": c.get("source"),
                    }
                )
            except Exception:
                continue

        body = {
            "target": target_block,
            "candidates": norm_candidates,
        }
        return "\n".join(header_lines) + "\n\n" + json.dumps(body, ensure_ascii=False)

    def _call_model(self, payload: Dict[str, Any]) -> Dict[str, Any] | None:
        import json
        from urllib.error import URLError, HTTPError
        from urllib.request import Request, urlopen

        data = json.dumps(payload).encode("utf-8")
        url = f"{self._base_url}/v1/chat/completions"
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        try:
            extra = getattr(self, "_headers", None) or {}
            if isinstance(extra, dict):
                headers.update({str(k): str(v) for k, v in extra.items()})
        except Exception:
            pass
        req = Request(url, data=data, headers=headers)
        try:
            with urlopen(req, timeout=self._timeout) as resp:
                resp_bytes = resp.read()
            try:
                preview = resp_bytes.decode("utf-8", errors="replace")
                if len(preview) > 1024:
                    preview = preview[:1024] + "...[truncated]"
                _log.warning("pagebrain.llm_ranker.raw_response_preview %s", preview)
            except Exception:
                pass
        except HTTPError as e:
            # Log minimal details so operators can see why the LLM path
            # fell back, without leaking payloads or secrets.
            try:
                status = getattr(e, "code", None)
                reason = getattr(e, "reason", None)
                message = None
                param = None
                try:
                    body = e.read() or b""
                    import json as _json

                    data = _json.loads(body.decode("utf-8", errors="ignore"))
                    if isinstance(data, dict):
                        err = data.get("error") or {}
                        if isinstance(err, dict):
                            message = err.get("message")
                            param = err.get("param")
                except Exception:
                    message = None
                    param = None
                _log.warning(
                    "pagebrain.llm_ranker.http_error status=%s reason=%s message=%s param=%s",
                    status,
                    reason,
                    message,
                    param,
                )
            except Exception:
                pass
            return None
        except URLError as e:
            try:
                reason = getattr(e, "reason", str(e))
                _log.warning(
                    "pagebrain.llm_ranker.url_error reason=%s",
                    reason,
                )
            except Exception:
                pass
            return None
        try:
            return json.loads(resp_bytes.decode("utf-8"))
        except Exception as e:
            try:
                _log.warning(
                    "pagebrain.llm_ranker.json_error error=%s",
                    type(e).__name__,
                )
            except Exception:
                pass
            return None

    @staticmethod
    def _extract_content(response_obj: Dict[str, Any]) -> str | None:
        """Extract the assistant message content from an OpenAI-like response.

        For Chat Completions, ``choices[0].message.content`` may be a string
        or a structured object (list/dict). We always return a string:
        - plain text is passed through;
        - structured content is JSON-encoded so the caller can treat it as a
          string and apply normal JSON parsing.
        """

        try:
            # Primary: Chat Completions style
            choices = response_obj.get("choices") or []
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message") or {}
                content = msg.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, (list, dict)):
                    import json as _json

                    try:
                        return _json.dumps(content, ensure_ascii=False)
                    except Exception:
                        return str(content)

            # Fallback: Responses-style `output`/`outputs`
            outputs = response_obj.get("output") or response_obj.get("outputs") or []
            if isinstance(outputs, list) and outputs:
                node = outputs[0] or {}
                content = node.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, (list, dict)):
                    import json as _json

                    try:
                        return _json.dumps(content, ensure_ascii=False)
                    except Exception:
                        return str(content)

            return None
        except Exception:
            return None

    @staticmethod
    def _validate_and_extract_ranking(result_obj: Dict[str, Any], n_candidates: int) -> List[int]:
        ranking_raw = result_obj.get("ranking")
        if not isinstance(ranking_raw, list):
            return []
        indices: List[int] = []
        for idx in ranking_raw:
            try:
                i = int(idx)
            except Exception:
                continue
            if 0 <= i < n_candidates:
                indices.append(i)
        # Ensure uniqueness and at least one candidate
        seen: set[int] = set()
        deduped: List[int] = []
        for i in indices:
            if i not in seen:
                seen.add(i)
                deduped.append(i)
        return deduped

    @staticmethod
    def _normalize_scores(scores_obj: Any, n_candidates: int) -> Dict[int, float]:
        scores: Dict[int, float] = {}
        if not isinstance(scores_obj, dict):
            return scores
        for k, v in scores_obj.items():
            try:
                idx = int(k)
            except Exception:
                continue
            if 0 <= idx < n_candidates:
                try:
                    scores[idx] = float(v)
                except Exception:
                    continue
        return scores


class OpenAiLlmPageBrainRanker(QwenLlmPageBrainRanker):
    """LLM ranker that talks to the public OpenAI API (e.g. gpt-5-mini).

    This subclasses ``QwenLlmPageBrainRanker`` so it reuses the same prompt
    builder and JSON validation helpers, but configures:
    - Authorization header with the provided API key.
    - ``response_format = {\"type\": \"json_object\"}`` to strongly bias the
      model toward valid JSON output.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com",
        timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__(base_url=base_url, model=model, timeout_seconds=timeout_seconds)
        # Attach auth + response_format for the parent implementation.
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._response_format = {"type": "json_object"}
        # Newer OpenAI chat/completions models often fix temperature=1.0 and
        # reject other values. Use the documented default.
        self._temperature = 1.0
        # Newer OpenAI chat/completions models use ``max_completion_tokens``
        # instead of ``max_tokens`` to cap output length.
        self._max_tokens_field = "max_completion_tokens"
        # GPT‑5 mini is a reasoning model and by default can spend most of its
        # budget on hidden chain-of-thought tokens. That leads to situations
        # where ``content`` is empty and ``finish_reason='length'`` even though
        # many completion tokens were consumed. To keep behaviour predictable
        # for PageBrain's small JSON responses, dial reasoning effort and
        # verbosity down.
        self._extra_params = {
            "reasoning_effort": "minimal",
            "verbosity": "low",
        }
