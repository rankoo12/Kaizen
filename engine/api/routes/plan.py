from __future__ import annotations

import time
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from engine.core.config.container import Container
from engine.core.validation.plan_validator import validate_plan, PlanValidationError
from engine.core.planning.planner import PlannerService, extract_plan_from_llm_response

router = APIRouter(prefix="/api", tags=["plan"])


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
    planner = PlannerService(llm=llm, settings=container.settings())

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

    prompt = planner.build_prompt(text, context)
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

    # Extract a JSON array from the response with multiple fallbacks.
    plan: Any = extract_plan_from_llm_response(raw)
    if plan is None or not isinstance(plan, list):
        # Final fallback: deterministic glue mapping to keep preview useful.
        try:
            plan = planner.glue_plan(text)
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
