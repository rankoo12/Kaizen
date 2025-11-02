from __future__ import annotations

from typing import Any, Dict


def build_planner_prompt(text: str, context: Dict[str, Any] | None = None) -> str:
    """Build a strict JSON-only prompt for the step planner.

    Mirrors the allowed tool shapes used by the preview route to reduce
    divergence between preview and live planning.
    """
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
