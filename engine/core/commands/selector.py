from __future__ import annotations

from typing import Any
import re


def to_selector_string(locator: Any) -> str:
    """Convert a locator dict or raw string into a Playwright selector string.

    Supported dict forms:
      - {"type": "css", "value": "..."}
      - {"type": "id", "value": "foo"} -> "#foo"
      - {"type": "testid", "value": "foo"} -> "[data-testid=\"foo\"]"
      - {"type": "text", "value": "Submit"} -> 'text="Submit"'
    Fallback: if unsupported, str(locator).
    """
    if isinstance(locator, str):
        return locator
    if isinstance(locator, dict):
        t = locator.get("type")
        v = locator.get("value")
        if isinstance(t, str) and isinstance(v, str):
            t = t.lower()
            if t == "css":
                return v
            if t == "id":
                return f"#{v}"
            if t == "testid":
                return f"[data-testid=\"{v}\"]"
            if t == "text":
                # Case-insensitive text match using regex
                esc = re.escape(v)
                return f"text=/{esc}/i"
    return str(locator)
