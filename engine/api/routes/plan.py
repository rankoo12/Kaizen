from __future__ import annotations

import json
import time
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from engine.core.config.container import Container
from engine.core.validation.plan_validator import validate_plan, PlanValidationError

router = APIRouter(prefix="/api", tags=["plan"])


def _build_prompt(text: str, context: Dict[str, Any] | None = None) -> str:
    ctx = context or {}
    preface = (
        "You are Kaizen's planner. Convert the instruction into a minimal JSON "
        "array of tool calls. Allowed tools and exact JSON shapes:\n"
        "- open: {\"tool\": \"open\", \"args\": {\"url\": string}}\n"
        "- click: {\"tool\": \"click\", \"args\": {\"target\": {\"text\": string|optional, \"css\": string|optional}}}\n"
        "- type: {\"tool\": \"type\", \"args\": {\"target\": {...}, \"text\": string}}\n"
        "- press: {\"tool\": \"press\", \"args\": {\"key\": string}}\n"
        "Rules: Respond with JSON ONLY, no prose. Use safe defaults.\n"
        "Output MUST be a JSON array (starts with '[' and ends with ']').\n"
        "Do NOT include any other keys like model/created_at/thinking.\n"
    )
    extras = []
    if isinstance(ctx.get("url"), str):
        extras.append(f"Current URL: {ctx['url']}")
    if isinstance(ctx.get("html"), str) and len(ctx["html"]) < 4000:
        extras.append("HTML snippet provided (truncated).")
    header = "\n".join([preface] + extras)
    fewshots = (
        "Example: 'press enter' -> [{\"tool\":\"press\",\"args\":{\"key\":\"Enter\"}}]\n"
        "Example: 'click Login' -> [{\"tool\":\"click\",\"args\":{\"target\":{\"text\":\"Login\"}}}]\n"
        "Example: 'type hello' -> [{\"tool\":\"type\",\"args\":{\"target\":{\"text\":\"input\"},\"text\":\"hello\"}}]\n\n"
    )
    return f"{header}\n{fewshots}Instruction: {text}\nJSON:"

def _glue_map(text: str) -> list[dict]:
    """Deterministic fallback mapping from plain text to minimal tool calls.

    Mirrors the glue mapping used by the live orchestrator so preview behaves
    consistently when LLM is slow or returns non-JSON.
    """
    t = (text or "").strip()
    lower = t.lower()
    plan: list[dict] = []
    if lower.startswith("click "):
        raw = t.split(" ", 1)[1].strip()
        css_like = False
        try:
            if raw.startswith(("#", ".", "[")):
                css_like = True
            elif raw.split("(")[0].lower().startswith(("input", "button", "a", "label", "form", "textarea", "select")):
                css_like = True
            elif "[" in raw or ":" in raw or ">" in raw or "=" in raw:
                css_like = True
        except Exception:
            css_like = False
        target = {"css": raw} if css_like else {"text": raw}
        plan.append({"tool": "click", "args": {"target": target}})
        return plan
    if lower.startswith("type "):
        typed = t.split(" ", 1)[1].strip()
        plan.append({"tool": "type", "args": {"target": {"text": "input"}, "text": typed}})
        return plan
    if lower.startswith("press "):
        key = t.split(" ", 1)[1].strip()
        plan.append({"tool": "press", "args": {"key": key}})
        return plan
    # default: map to a click by text (conservative)
    plan.append({"tool": "click", "args": {"target": {"text": t}}})
    return plan


@router.post("/plan/preview")
def preview_plan(request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
    text = (body or {}).get("text")
    context = (body or {}).get("context") or {}
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="'text' is required")

    container = Container()
    # Rate limit per API key (preferred) or client IP
    try:
        st = container.settings()
        window = int(getattr(st, "PREVIEW_RATE_WINDOW_SEC", 60) or 60)
        max_req = int(getattr(st, "PREVIEW_RATE_MAX_REQUESTS", 30) or 30)
    except Exception:
        window, max_req = 60, 30
    # simple per-process sliding window limiter
    global _rl_store
    try:
        _rl_store
    except NameError:
        _rl_store = {}
    now = int(time.time())
    key = request.headers.get("X-API-Key") or (request.client.host if request.client else "global")
    bucket = _rl_store.setdefault(str(key), [])
    cutoff = now - window + 1
    bucket[:] = [ts for ts in bucket if ts >= cutoff]
    if len(bucket) >= max_req:
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    bucket.append(now)
    llm = container.llm_text()
    if llm is None:
        raise HTTPException(status_code=501, detail="LLM is not enabled (set KAIZEN_LLM_ENABLED=true)")

    # Input caps
    try:
        max_text = int(getattr(st, "PREVIEW_INPUT_TEXT_MAX_CHARS", 500) or 500)
        max_html = int(getattr(st, "PREVIEW_CONTEXT_HTML_MAX_CHARS", 4000) or 4000)
    except Exception:
        max_text, max_html = 500, 4000
    if len(text) > max_text:
        text = text[:max_text]
    if isinstance(context.get("html"), str) and len(context["html"]) > max_html:
        context = dict(context)
        context["html"] = context["html"][:max_html]

    prompt = _build_prompt(text, context)
    raw: str
    # Optional tracing
    _span_cm = None
    try:
        from opentelemetry import trace as _trace  # type: ignore

        tracer = _trace.get_tracer("kaizen.engine.api")
        _span_cm = tracer.start_as_current_span("planner.preview")
        _span_cm.__enter__()
        span = _trace.get_current_span()
        try:
            span.set_attribute("model", getattr(Container().settings(), "OLLAMA_MODEL", ""))
        except Exception:
            pass
    except Exception:
        _span_cm = None

    try:
        raw = llm.ask(prompt)
    except Exception as e:
        if _span_cm is not None:
            try:
                from opentelemetry.trace import Status, StatusCode  # type: ignore

                _trace.get_current_span().set_status(Status(StatusCode.ERROR))  # type: ignore
            except Exception:
                pass
        raise HTTPException(status_code=502, detail=f"llm error: {e}")

    # Extract a JSON array from the response with multiple fallbacks
    plan: Any = None
    # 1) Direct parse
    try:
        plan = json.loads(raw)
    except Exception:
        plan = None
    # 2) If parsed as object, try typical fields that carry content
    if isinstance(plan, dict):
        # Some models return a wrapper object; try 'response' or chat 'message.content'
        content = plan.get("response") if isinstance(plan.get("response"), str) else None
        if not content:
            msg = plan.get("message")
            if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                content = msg.get("content")
        if content:
            try:
                plan = json.loads(content)
            except Exception:
                plan = None
    # 3) Heuristic: bracket slice from the raw string
    if not isinstance(plan, list):
        try:
            raw2 = raw.strip()
            if raw2.startswith("```"):
                # strip code fences like ```json\n...\n```
                raw2 = raw2.strip("`")
            start = raw2.find("[")
            end = raw2.rfind("]") + 1
            if start >= 0 and end > start:
                plan = json.loads(raw2[start:end])
        except Exception:
            plan = None
    if plan is None or not isinstance(plan, list):
        # Final fallback: deterministic glue mapping to keep preview useful
        try:
            plan = _glue_map(text)
        except Exception:
            plan = None
    if plan is None:
        raise HTTPException(status_code=502, detail="llm returned non-JSON")

    try:
        validate_plan(plan)
        valid = True
        errors: list[str] = []
    except PlanValidationError as e:
        valid = False
        errors = list(e.errors or [])

    resp = {
        "plan": plan,
        "valid": valid,
        "errors": errors,
        "model": getattr(container.settings(), "OLLAMA_MODEL", None),
    }

    if _span_cm is not None:
        try:
            from opentelemetry import trace as _trace  # type: ignore
            span = _trace.get_current_span()
            span.set_attribute("ok", bool(valid))  # type: ignore
        except Exception:
            pass
        try:
            _span_cm.__exit__(None, None, None)
        except Exception:
            pass

    return resp
