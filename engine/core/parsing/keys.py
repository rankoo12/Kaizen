from __future__ import annotations


def normalize_key_name(raw: str) -> str:
    """Normalize human-entered key names to Playwright-compatible tokens.

    Examples:
      - "enter" -> "Enter"
      - "esc"/"escape" -> "Escape"
      - "ctrl+a"/"Control + a" -> "Control+A"
      - "cmd+a"/"meta+a" -> "Meta+A"
      - arrow keys -> "ArrowLeft"/"ArrowRight"/"ArrowUp"/"ArrowDown"
    """
    if not isinstance(raw, str) or not raw.strip():
        return ""
    s = raw.strip()
    low = s.lower().replace(" ", "")

    # Single keys
    singles = {
        "enter": "Enter",
        "return": "Enter",
        "esc": "Escape",
        "escape": "Escape",
        "tab": "Tab",
        "backspace": "Backspace",
        "delete": "Delete",
        "space": "Space",
        "pagedown": "PageDown",
        "pageup": "PageUp",
        "home": "Home",
        "end": "End",
    }
    if low in singles:
        return singles[low]

    # Arrow keys
    if low in {"arrowleft", "left", "leftarrow"}:
        return "ArrowLeft"
    if low in {"arrowright", "right", "rightarrow"}:
        return "ArrowRight"
    if low in {"arrowup", "up", "uparrow"}:
        return "ArrowUp"
    if low in {"arrowdown", "down", "downarrow"}:
        return "ArrowDown"

    # Chord like ctrl+a, control+a, cmd+a, meta+a
    # Accept separators '+', '-', ' + '
    for sep in ("+", "-"):
        if sep in low:
            parts = [p for p in low.split(sep) if p]
            if len(parts) == 2:
                mod, key = parts
                mod_map = {
                    "ctrl": "Control",
                    "control": "Control",
                    "cmd": "Meta",
                    "meta": "Meta",
                    "alt": "Alt",
                    "shift": "Shift",
                }
                m = mod_map.get(mod, mod.capitalize())
                # Normalize key portion also via singles
                k = normalize_key_name(key)
                if not k:
                    k = key.upper() if len(key) == 1 else key.capitalize()
                return f"{m}+{k}"

    # Fallback: capitalize first letter, preserve rest when meaningful
    if len(s) == 1:
        return s.upper()
    return s[:1].upper() + s[1:]
