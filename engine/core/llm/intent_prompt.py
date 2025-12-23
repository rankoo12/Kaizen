from __future__ import annotations


def build_intent_prompt(text: str, tool: str | None = None) -> str:
    """Build a strict JSON-only prompt for intent extraction."""
    tool_name = (tool or "").strip().lower()
    header = (
        "You are Kaizen's intent parser. Extract the target noun and any ordinal position.\n"
        "Return JSON only, no prose.\n"
        "Schema:\n"
        '{ "noun": string|null, "ordinal": integer|null, "position": "last"|null }\n'
        "Rules:\n"
        "- noun should be the thing the user refers to (e.g. 'video', 'result', 'search box').\n"
        "- ordinal is 1-based (first=1, second=2, etc).\n"
        "- use position='last' only when the user says last/final.\n"
        "- if unknown, return nulls.\n"
    )
    if tool_name:
        header += f"Tool: {tool_name}\n"
    examples = (
        "Examples:\n"
        "Input: click the second video\n"
        'Output: {"noun":"video","ordinal":2,"position":null}\n'
        "Input: click the last result\n"
        'Output: {"noun":"result","ordinal":null,"position":"last"}\n'
        "Input: type hello in the third search box\n"
        'Output: {"noun":"search box","ordinal":3,"position":null}\n'
        "Input: click login\n"
        'Output: {"noun":"login","ordinal":null,"position":null}\n'
    )
    return f"{header}\n{examples}\nInput: {text}\nOutput:"
