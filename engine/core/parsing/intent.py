from __future__ import annotations

from typing import Tuple
import re

_ORDINAL_WORDS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}


def _parse_ordinal_token(token: str) -> Tuple[int | None, str | None]:
    if not isinstance(token, str):
        return None, None
    t = token.strip().lower()
    if not t:
        return None, None
    if t in {"last", "final"}:
        return -1, "last"
    if t in _ORDINAL_WORDS:
        return _ORDINAL_WORDS[t], "index"
    m = re.match(r"^(\d+)(st|nd|rd|th)?$", t)
    if m:
        try:
            val = int(m.group(1))
            return val, "index"
        except Exception:
            return None, None
    return None, None


def extract_ordinal_and_noun(phrase: str) -> dict:
    """Extract ordinal + noun from a phrase like 'second video'."""
    if not isinstance(phrase, str):
        return {}
    raw = phrase.strip()
    if not raw:
        return {}
    pattern = r"(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last|final|\d+(?:st|nd|rd|th)?)"
    m = re.search(rf"\b{pattern}\b\s+(?P<noun>.+)", raw, flags=re.IGNORECASE)
    if not m:
        return {}
    ord_token = m.group(1)
    noun = (m.group("noun") or "").strip()
    ordinal, position = _parse_ordinal_token(ord_token)
    out = {}
    if ordinal is not None:
        out["ordinal"] = ordinal
    if position:
        out["position"] = position
    if noun:
        out["noun"] = noun
    return out


def parse_intent(step_text: str, tool: str | None = None) -> dict:
    """Lightweight intent parser for ordinal references in steps."""
    if not isinstance(step_text, str):
        return {}
    raw = step_text.strip()
    if not raw:
        return {}

    out: dict = {}
    tool_l = (tool or "").strip().lower()
    lower = raw.lower()

    if not tool_l:
        for verb in ("click", "tap", "select", "choose", "open", "type", "enter", "write"):
            if lower.startswith(f"{verb} "):
                tool_l = verb
                break

    ord_pattern = r"(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last|final|\d+(?:st|nd|rd|th)?)"

    if tool_l in {"click", "tap", "select", "choose", "open"}:
        m = re.search(
            rf"\b{tool_l}\b\s+(?:on\s+)?(?:the\s+)?(?P<ord>{ord_pattern})\s+(?P<noun>.+)",
            raw,
            flags=re.IGNORECASE,
        )
        if m:
            ordinal, position = _parse_ordinal_token(m.group("ord") or "")
            noun = (m.group("noun") or "").strip()
            if ordinal is not None:
                out["ordinal"] = ordinal
            if position:
                out["position"] = position
            if noun:
                out["noun"] = noun
            return out

    if tool_l in {"type", "enter", "write"}:
        m2 = re.search(
            rf"\b(?:in|into|inside)\s+(?:the\s+)?(?P<ord>{ord_pattern})\s+(?P<noun>.+)",
            raw,
            flags=re.IGNORECASE,
        )
        if m2:
            ordinal, position = _parse_ordinal_token(m2.group("ord") or "")
            noun = (m2.group("noun") or "").strip()
            if ordinal is not None:
                out["ordinal"] = ordinal
            if position:
                out["position"] = position
            if noun:
                out["noun"] = noun
            return out

    return extract_ordinal_and_noun(raw)


def split_type_step(step_text: str) -> Tuple[str | None, str | None]:
    """Split 'type X in the second search box' into (X, 'second search box')."""
    if not isinstance(step_text, str):
        return None, None
    raw = step_text.strip()
    if not raw:
        return None, None
    m = re.match(
        r"^\s*(type|enter|write)\s+(?P<typed>.+?)\s+(?:in|into|inside)\s+(?P<target>.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if not m:
        return None, None
    typed = (m.group("typed") or "").strip().strip("\"'")
    target = (m.group("target") or "").strip()
    return typed or None, target or None
