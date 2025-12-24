from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Optional

from engine.core.llm.plan_prompt import build_planner_prompt
from engine.core.parsing.intent import parse_intent, split_type_step
from engine.core.parsing.keys import normalize_key_name


IntentResolver = Callable[[str, Optional[str]], dict]


def _is_css_like(raw: str) -> bool:
    try:
        if raw.startswith(("#", ".", "[")):
            return True
        head = raw.split("(", 1)[0].lower()
        if head.startswith(("input", "button", "a", "label", "form", "textarea", "select")):
            return True
        if "[" in raw or ":" in raw or ">" in raw or "=" in raw:
            return True
    except Exception:
        return False
    return False


def glue_plan(text: str, *, llm_intent_resolver: IntentResolver | None = None) -> list[dict]:
    """Deterministic fallback mapping from plain text to minimal tool calls."""
    t = (text or "").strip()
    lower = t.lower()
    plan: list[dict] = []

    # Navigation and scroll intents first.
    if "go back" in lower or lower.strip() in {"back", "previous page", "previous screen"}:
        plan.append({"tool": "back", "args": {}})
        return plan
    if "go forward" in lower or "next page" in lower or "next screen" in lower or lower.strip() in {"forward"}:
        plan.append({"tool": "forward", "args": {}})
        return plan
    if "reload" in lower or "refresh" in lower:
        plan.append({"tool": "reload", "args": {}})
        return plan

    # Tab/window navigation.
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

    # Simple QA assertions and submits.
    if lower.startswith(("assert ", "check ", "verify ")):
        if "url contains" in lower:
            m = re.search(r"url\s+contains\s+(\S+)", lower)
            expected = None
            if m:
                expected = m.group(1).strip(" .'\"")
            if expected:
                plan.append({"tool": "assertUrl", "args": {"expected": expected, "match": "contains"}})
                return plan
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
        raw = t.split(" ", 1)[1].strip() or ""
        if _is_css_like(raw):
            target = {"css": raw}
        else:
            intent = parse_intent(t, tool="click")
            if not intent and llm_intent_resolver is not None:
                intent = llm_intent_resolver(t, "click")
            noun = intent.get("noun") if isinstance(intent, dict) else None
            target_text = noun if isinstance(noun, str) and noun else raw
            target = {"text": target_text}
            if intent:
                target["__intent"] = intent
        plan.append({"tool": "click", "args": {"target": target}})
        return plan

    if lower.startswith(("type ", "enter ", "write ")):
        typed, target_phrase = split_type_step(t)
        if not typed:
            typed = t.split(" ", 1)[1].strip()
        intent = parse_intent(target_phrase or t, tool="type")
        if not intent and llm_intent_resolver is not None:
            intent = llm_intent_resolver(target_phrase or t, "type")
        noun = intent.get("noun") if isinstance(intent, dict) else None
        target_text = noun if isinstance(noun, str) and noun else "input"
        target = {"text": target_text}
        if intent:
            target["__intent"] = intent
        plan.append({"tool": "type", "args": {"target": target, "text": typed}})
        return plan

    if lower.startswith("press "):
        key_raw = t.split(" ", 1)[1].strip()
        try:
            key = normalize_key_name(key_raw)
        except Exception:
            key = key_raw
        plan.append({"tool": "press", "args": {"key": key}})
        return plan

    # Default: map to a click by text (conservative).
    plan.append({"tool": "click", "args": {"target": {"text": t}}})
    return plan


def _strip_code_fences(raw: str) -> str:
    text = raw.strip()
    if not text.startswith("```"):
        return text
    # Remove leading ```json? and trailing ```
    text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


def extract_plan_from_llm_response(raw: str) -> list[dict] | None:
    """Parse a JSON plan array from LLM output with wrapper fallbacks."""
    if not isinstance(raw, str) or not raw.strip():
        return None

    plan: Any = None
    try:
        plan = json.loads(raw)
    except Exception:
        plan = None

    # If parsed as object, try common wrapper shapes.
    if isinstance(plan, dict):
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

    # Accept single tool dicts.
    if isinstance(plan, dict) and "tool" in plan and "args" in plan:
        plan = [plan]

    # Heuristic bracket slice from raw string.
    if not isinstance(plan, list):
        try:
            raw2 = _strip_code_fences(raw)
            start = raw2.find("[")
            end = raw2.rfind("]") + 1
            if start >= 0 and end > start:
                plan = json.loads(raw2[start:end])
        except Exception:
            plan = None

    return plan if isinstance(plan, list) else None


class PlannerService:
    def __init__(self, *, llm: Any | None, settings: Any | None = None) -> None:
        self._llm = llm
        self._settings = settings

    def build_prompt(self, text: str, context: Dict[str, Any] | None = None) -> str:
        return build_planner_prompt(text, context)

    def llm_plan(self, text: str, context: Dict[str, Any] | None = None) -> list[dict] | None:
        if self._llm is None:
            return None
        prompt = self.build_prompt(text, context)
        raw = self._llm.ask(prompt)
        return extract_plan_from_llm_response(raw)

    def glue_plan(self, text: str, *, llm_intent_resolver: IntentResolver | None = None) -> list[dict]:
        return glue_plan(text, llm_intent_resolver=llm_intent_resolver)


__all__ = ["PlannerService", "glue_plan", "extract_plan_from_llm_response"]
