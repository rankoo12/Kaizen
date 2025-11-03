from __future__ import annotations


def parse_steps_text(steps_text: str) -> list[dict]:
    """Turn multi-line plain text into a list of step dicts.

    - Splits on newlines; trims whitespace
    - Skips empty/commented lines (lines starting with '#')
    - Returns list of {"text": <line>}
    """
    steps: list[dict] = []
    if not isinstance(steps_text, str):
        return steps
    for raw in steps_text.splitlines():
        line = (raw or "").strip()
        if not line or line.startswith("#"):
            continue
        steps.append({"text": line})
    return steps
