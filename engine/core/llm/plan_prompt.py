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
        "Rules: Respond with JSON ONLY (no prose). Output MUST be a JSON array. "
        "Do NOT include keys like model/created_at/thinking/analysis/steps/result. "
        "Do NOT wrap the array inside another object (for example, do not return {\"plan\":[...]}). "
        "Do NOT invent new tool names; pick the closest tool from the list.\n"
    )
    extras = []
    if isinstance(ctx.get("url"), str):
        extras.append(f"Current URL: {ctx['url']}")
    if isinstance(ctx.get("html"), str) and len(ctx["html"]) < 4000:
        extras.append("HTML snippet provided (truncated).")
    header = "\n".join([preface] + extras)
    examples = (
        "Examples:\n"
        "- 'press enter' -> [{\"tool\":\"press\",\"args\":{\"key\":\"Enter\"}}]\n"
        "- 'click Login' -> [{\"tool\":\"click\",\"args\":{\"target\":{\"text\":\"Login\"}}}]\n"
        "- 'type hello into the search box' -> [{\"tool\":\"type\",\"args\":{\"target\":{\"text\":\"search\"},\"text\":\"hello\"}}]\n"
        "- 'go back' -> [{\"tool\":\"back\",\"args\":{}}]\n"
        "- 'reload the page' -> [{\"tool\":\"reload\",\"args\":{}}]\n"
        "- 'scroll down a bit' -> [{\"tool\":\"scroll\",\"args\":{\"direction\":\"down\",\"amount\":400}}]\n"
        "- 'open the dashboard in a new tab' -> [{\"tool\":\"newTab\",\"args\":{\"url\":\"https://app.example.com/dashboard\"}}]\n"
        "- 'select \"Israel\" from the country dropdown' -> [{\"tool\":\"select\",\"args\":{\"target\":{\"text\":\"country\"},\"option\":{\"label\":\"Israel\"}}}]\n"
        "- 'upload \"resume.pdf\"' -> [{\"tool\":\"upload\",\"args\":{\"target\":{\"text\":\"Upload\"},\"files\":[\"resume.pdf\"]}}]\n"
        "- 'drag card A onto column B' -> [{\"tool\":\"dragAndDrop\",\"args\":{\"target\":{\"text\":\"card A\"},\"to\":{\"text\":\"column B\"}}}]\n"
        "- 'wait for the Login button to be visible' -> [{\"tool\":\"waitFor\",\"args\":{\"target\":{\"text\":\"Login\"},\"state\":\"visible\"}}]\n"
        "- 'download the report' -> [{\"tool\":\"download\",\"args\":{\"target\":{\"text\":\"report\"}}}]\n"
        "- 'check that the URL contains /dashboard' -> [{\"tool\":\"assertUrl\",\"args\":{\"expected\":\"/dashboard\",\"match\":\"contains\"}}]\n"
        "- 'submit the form' -> [{\"tool\":\"press\",\"args\":{\"key\":\"Enter\"}}]\n"
        "- 'assert that Invalid password error is shown' -> [{\"tool\":\"assertText\",\"args\":{\"target\":{\"text\":\"Invalid password\"},\"expected\":\"Invalid password\",\"match\":\"contains\"}}]\n"
        "- 'fill the login form and go to the dashboard' -> ["
        "{\"tool\":\"type\",\"args\":{\"target\":{\"text\":\"Email\"},\"text\":\"user@example.com\"}},"
        "{\"tool\":\"type\",\"args\":{\"target\":{\"text\":\"Password\"},\"text\":\"secret\"}},"
        "{\"tool\":\"press\",\"args\":{\"key\":\"Enter\"}},"
        "{\"tool\":\"assertUrl\",\"args\":{\"expected\":\"/dashboard\",\"match\":\"contains\"}}"
        "]\n\n"
    )
    return f"{header}\n{examples}Instruction: {text}\nJSON:"
