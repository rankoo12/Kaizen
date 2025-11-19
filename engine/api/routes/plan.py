from __future__ import annotations

import json
import time
from typing import Any, Dict

import re

from fastapi import APIRouter, HTTPException, Request

from engine.core.config.container import Container
from engine.core.validation.plan_validator import validate_plan, PlanValidationError

router = APIRouter(prefix="/api", tags=["plan"])


def _build_prompt(text: str, context: Dict[str, Any] | None = None) -> str:
    ctx = context or {}
    preface = (
        "You are Kaizen's planner. Convert the instruction into a minimal JSON "
        "array of tool calls. Use only these tools and shapes:\n"
        "- open: {\"tool\":\"open\",\"args\":{\"url\": string}}\n"
        "- click: {\"tool\":\"click\",\"args\":{\"target\":{\"text\": string|optional,\"css\": string|optional}}}\n"
        "- doubleClick/rightClick/hover/focus/blur/clear: same shape as click; only \"tool\" changes.\n"
        "- type: {\"tool\":\"type\",\"args\":{\"target\": {...},\"text\": string,\"clear\": boolean|optional}}\n"
        "- select: {\"tool\":\"select\",\"args\":{\"target\": {...},\"option\": {\"value\"|\"label\"|\"index\": ...}}}\n"
        "- upload: {\"tool\":\"upload\",\"args\":{\"target\": {...},\"files\": [string,...]}}\n"
        "- drag: {\"tool\":\"drag\",\"args\":{\"target\": {...},\"dx\": integer,\"dy\": integer}}\n"
        "- dragAndDrop: {\"tool\":\"dragAndDrop\",\"args\":{\"target\": {...},\"to\": {...}}}\n"
        "- press: {\"tool\":\"press\",\"args\":{\"key\": string}}\n"
        "- waitFor: {\"tool\":\"waitFor\",\"args\":{\"target\": {...}|optional,\"url\": string|optional,\"urlContains\": string|optional,\"state\": \"visible\"|\"hidden\"|\"clickable\"|\"networkidle\"|\"raf\"|optional,\"text\": string|optional,\"match\": \"equals\"|\"contains\"|\"regex\"|optional,\"timeout\": integer|optional,\"sleepMs\": integer|optional,\"frames\": integer|optional}}\n"
        "- scroll: {\"tool\":\"scroll\",\"args\":{\"direction\": \"up\"|\"down\"|\"left\"|\"right\",\"amount\": integer}} OR {\"x\": integer,\"y\": integer}\n"
        "- reload/back/forward: {\"tool\":\"reload\"|\"back\"|\"forward\",\"args\":{}}\n"
        "- newTab/newWindow: {\"tool\":\"newTab\"|\"newWindow\",\"args\":{\"url\": string|optional}}\n"
        "- switchTab/switchWindow: {\"tool\":\"switchTab\"|\"switchWindow\",\"args\":{\"index\": integer|optional,\"urlContains\": string|optional,\"titleContains\": string|optional}}\n"
        "- closeTab/closeWindow: {\"tool\":\"closeTab\"|\"closeWindow\",\"args\":{\"index\": integer|optional}}\n"
        "- download: {\"tool\":\"download\",\"args\":{\"target\": {...}|optional,\"url\": string|optional,\"filename\": string|optional,\"checksum\": string|optional,\"algo\": \"sha256\"|optional}}\n"
        "- assertVisible/assertText/assertUrl/custom: only use when explicitly asked to assert or run a custom script; args follow the tool name (for example, assertVisible.args.target, assertText.args.expected).\n"
        "Rules: Respond with JSON ONLY, no prose. Use safe defaults. "
        "Output MUST be a JSON array (starts with '[' and ends with ']'). "
        "Do NOT include any other keys like model/created_at/thinking/analysis/steps/result. "
        "Do NOT wrap the array inside another object (for example, do not return {\"plan\":[...]}). "
        "Do NOT invent new tool names; pick the closest tool from the list.\n"
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
        "Example: 'type hello' -> [{\"tool\":\"type\",\"args\":{\"target\":{\"text\":\"input\"},\"text\":\"hello\"}}]\n"
        "Example: 'go back' -> [{\"tool\":\"back\",\"args\":{}}]\n"
        "Example: 'reload the page' -> [{\"tool\":\"reload\",\"args\":{}}]\n"
        "Example: 'scroll down a bit' -> [{\"tool\":\"scroll\",\"args\":{\"direction\":\"down\",\"amount\":400}}]\n"
        "Example: 'open the dashboard in a new tab' -> [{\"tool\":\"newTab\",\"args\":{\"url\":\"https://app.example.com/dashboard\"}}]\n"
        "Example: 'download the report' -> [{\"tool\":\"download\",\"args\":{\"target\":{\"text\":\"report\"}}}]\n"
        "Example: 'check that the URL contains /dashboard' -> [{\"tool\":\"assertUrl\",\"args\":{\"expected\":\"/dashboard\",\"match\":\"contains\"}}]\n"
        "Example: 'submit the form' -> [{\"tool\":\"press\",\"args\":{\"key\":\"Enter\"}}]\n"
        "Example: 'assert that Invalid password error is shown' -> [{\"tool\":\"assertText\",\"args\":{\"target\":{\"text\":\"Invalid password\"},\"expected\":\"Invalid password\",\"match\":\"contains\"}}]\n"
        "Example: 'fill the login form and go to the dashboard' -> ["
        "{\"tool\":\"type\",\"args\":{\"target\":{\"text\":\"Email\"},\"text\":\"user@example.com\"}},"
        "{\"tool\":\"type\",\"args\":{\"target\":{\"text\":\"Password\"},\"text\":\"secret\"}},"
        "{\"tool\":\"press\",\"args\":{\"key\":\"Enter\"}},"
        "{\"tool\":\"assertUrl\",\"args\":{\"expected\":\"/dashboard\",\"match\":\"contains\"}}"
        "]\n\n"
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
    # Navigation and scroll intents first
    if "go back" in lower or lower.strip() in {"back", "previous page", "previous screen"}:
        plan.append({"tool": "back", "args": {}})
        return plan
    if "go forward" in lower or "next page" in lower or "next screen" in lower or lower.strip() in {"forward"}:
        plan.append({"tool": "forward", "args": {}})
        return plan
    if "reload" in lower or "refresh" in lower:
        plan.append({"tool": "reload", "args": {}})
        return plan
    # Tab/window navigation
    if "first tab" in lower and "switch" in lower:
        plan.append({"tool": "switchTab", "args": {"index": 0}})
        return plan
    if "new tab" in lower:
        plan.append({"tool": "newTab", "args": {}})
        return plan
    if "new window" in lower:
        plan.append({"tool": "newWindow", "args": {}})
        return plan
    if "switch to tab" in lower or "go to tab" in lower:
        m = re.search(r"tab\s+(\d+)", lower)
        if m:
            args: dict[str, Any] = {}
            try:
                idx = max(int(m.group(1)) - 1, 0)
                args["index"] = idx
            except Exception:
                pass
            if args:
                plan.append({"tool": "switchTab", "args": args})
                return plan
    if "switch to window" in lower or "go to window" in lower:
        m = re.search(r"window\s+(\d+)", lower)
        if m:
            args2: dict[str, Any] = {}
            try:
                idx2 = max(int(m.group(1)) - 1, 0)
                args2["index"] = idx2
            except Exception:
                pass
            if args2:
                plan.append({"tool": "switchWindow", "args": args2})
                return plan
    if "close current tab" in lower or "close the current tab" in lower or lower.strip() in {"close tab", "close this tab"}:
        plan.append({"tool": "closeTab", "args": {}})
        return plan
    if "close current window" in lower or lower.strip() in {"close window", "close this window"}:
        plan.append({"tool": "closeWindow", "args": {}})
        return plan
    # Simple QA assertions and submits
    if lower.startswith(("assert ", "check ", "verify ")):
        if "url contains" in lower:
            m = re.search(r"url\s+contains\s+(\S+)", lower)
            expected = None
            if m:
                expected = m.group(1).strip(" .'\"")
            if expected:
                plan.append({"tool": "assertUrl", "args": {"expected": expected, "match": "contains"}})
                return plan
        # Error/message text assertion when a quoted string is present
        if "'" in t or '"' in t:
            m = re.search(r"'([^']+)'", t)
            if not m:
                m = re.search(r"\"([^\"]+)\"", t)
            expected_text = m.group(1).strip() if m else ""
            if expected_text:
                plan.append(
                    {
                        "tool": "assertText",
                        "args": {
                            "target": {"text": expected_text},
                            "expected": expected_text,
                            "match": "contains",
                        },
                    }
                )
                return plan
    if "submit the form" in lower or "submit form" in lower or (lower.startswith("submit ") and " form" in lower):
        plan.append({"tool": "press", "args": {"key": "Enter"}})
        return plan
    if lower.startswith("scroll"):
        direction = "down"
        if "up" in lower or "top" in lower:
            direction = "up"
        elif "left" in lower:
            direction = "left"
        elif "right" in lower:
            direction = "right"
        amount = 400
        plan.append({"tool": "scroll", "args": {"direction": direction, "amount": amount}})
        return plan
    if lower.startswith("download "):
        label = t.split(" ", 1)[1].strip()
        plan.append({"tool": "download", "args": {"target": {"text": label}}})
        return plan
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
        # Some models return a wrapper object; handle a few common shapes:
        # - {"plan": [ ... ]}
        # - {"response": "[...]"}
        # - {"message": {"content": "[...]"}} (chat-style)
        # - {"choices":[{"message":{"content":"[...]"}}, ...]} (OpenAI-style)
        if isinstance(plan.get("plan"), list):
            plan = plan.get("plan")
        else:
            content = plan.get("response") if isinstance(plan.get("response"), str) else None
            if not content:
                msg = plan.get("message")
                if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                    content = msg.get("content")
            if not content:
                choices = plan.get("choices")
                if isinstance(choices, list) and choices:
                    first = choices[0] or {}
                    msg = first.get("message") or first.get("delta") or {}
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
