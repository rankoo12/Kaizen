from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

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
    )
    extras = []
    if isinstance(ctx.get("url"), str):
        extras.append(f"Current URL: {ctx['url']}")
    if isinstance(ctx.get("html"), str) and len(ctx["html"]) < 4000:
        extras.append("HTML snippet provided (truncated).")
    header = "\n".join([preface] + extras)
    example = (
        "Example: 'press enter' -> [{\"tool\":\"press\",\"args\":{\"key\":\"Enter\"}}]\n\n"
    )
    return f"{header}\n{example}Instruction: {text}\nJSON:"


@router.post("/plan/preview")
def preview_plan(body: Dict[str, Any]) -> Dict[str, Any]:
    text = (body or {}).get("text")
    context = (body or {}).get("context") or {}
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="'text' is required")

    container = Container()
    llm = container.llm_text()
    if llm is None:
        raise HTTPException(status_code=501, detail="LLM is not enabled (set KAIZEN_LLM_ENABLED=true)")

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

    # Extract JSON array from response
    plan: Any = None
    try:
        plan = json.loads(raw)
    except Exception:
        # heuristic: locate first '[' and last ']'
        try:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start >= 0 and end > start:
                plan = json.loads(raw[start:end])
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
