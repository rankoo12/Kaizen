from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import re

from engine.core.resolving.element_resolver import ElementResolver


_TAG_RX = re.compile(r"<\s*(/)?\s*([a-zA-Z0-9:-]+)([^>]*)>", re.IGNORECASE | re.DOTALL)
_ATTR_RX = re.compile(r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*\"([^\"]*)\"", re.IGNORECASE)


def _extract_text_blocks(html: str, tag: str) -> Dict[str, str]:
    """Return a map of a synthetic key to innerText for tags that have bodies.

    Not a full HTML parser; best-effort extraction to enrich candidates.
    """
    out: Dict[str, str] = {}
    try:
        pattern = re.compile(
            rf"<\s*{tag}[^>]*>(.*?)</\s*{tag}\s*>",
            re.IGNORECASE | re.DOTALL,
        )
        i = 0
        for m in pattern.finditer(html):
            text = re.sub(r"\s+", " ", m.group(1)).strip()
            out[f"{tag}#{i}"] = text
            i += 1
    except Exception:
        pass
    return out


def _parse_attrs(attr_blob: str) -> Dict[str, str]:
    attrs: Dict[str, str] = {}
    for k, v in _ATTR_RX.findall(attr_blob or ""):
        lk = k.lower()
        attrs[lk] = v
    return attrs


def _extract_candidates_from_html(html: str) -> List[dict]:
    """Very lightweight candidate extraction for snapshot HTML.

    Captures inputs, selects, textareas, buttons, anchors, and role=button nodes.
    """
    btn_text = _extract_text_blocks(html, "button")
    a_text = _extract_text_blocks(html, "a")
    label_text = _extract_text_blocks(html, "label")

    # Map 'for' -> label text
    label_for: Dict[str, str] = {}
    try:
        for m in re.finditer(r"<\s*label([^>]*)>", html, re.IGNORECASE | re.DOTALL):
            attrs = _parse_attrs(m.group(1))
            la = attrs.get("for")
            if la:
                # find a close label block text with same index if available
                # fallback to any label text
                label_for[la] = label_text.get("label#0", "")
    except Exception:
        pass

    candidates: List[dict] = []
    idx_map = {"button": 0, "a": 0}
    for m in _TAG_RX.finditer(html):
        closing, tag, attrs_blob = m.groups()
        if closing:
            continue
        ltag = (tag or "").lower()
        if ltag not in ("input", "select", "textarea", "button", "a"):
            # also include any [role="button"]
            attrs = _parse_attrs(attrs_blob)
            if attrs.get("role", "").lower() != "button":
                continue
        attrs = _parse_attrs(attrs_blob)

        role = attrs.get("role", "").lower()
        if role != "button":
            role = "button" if ltag in ("button",) else role

        classes = (attrs.get("class", "").split() if attrs.get("class") else [])
        text_val = ""
        if ltag == "button":
            key = f"button#{idx_map['button']}"
            text_val = btn_text.get(key, "")
            idx_map["button"] += 1
        elif ltag == "a":
            key = f"a#{idx_map['a']}"
            text_val = a_text.get(key, "")
            idx_map["a"] += 1

        # labels array
        labels = []
        lid = attrs.get("id")
        if lid and lid in label_for and label_for[lid]:
            labels.append(label_for[lid])

        cand = {
            "tag": ltag,
            "id": attrs.get("id", ""),
            "classes": classes,
            "role": role,
            "text": text_val,
            "aria_label": attrs.get("aria-label", ""),
            "visible": True,
            "clickable": ltag in ("button", "a", "input"),
            "bbox": {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0},
            # extra fields the resolver/strategies may consult
            "attrs": {
                "testid": attrs.get("data-testid") or attrs.get("testid") or "",
            },
            "name": attrs.get("name", ""),
            "placeholder": attrs.get("placeholder", ""),
            "value": attrs.get("value", ""),
            "type": attrs.get("type", "").lower(),
            "labels": labels,
        }
        candidates.append(cand)

    return candidates


def resolve_snapshot(*, plan, html_path: str | None, tolerance: float, healer_depth: int) -> Dict[str, Any]:
    """Resolve a snapshot step using static HTML as the candidate source.

    Produces a minimal resolve payload containing candidates and the chosen locator.
    """
    html = ""
    if html_path:
        p = Path(html_path)
        try:
            html = p.read_text(encoding="utf-8")
        except Exception:
            html = ""
    candidates = _extract_candidates_from_html(html) if html else []
    # Build a query from planner output
    query: Dict[str, Any] = {}
    try:
        q = getattr(plan, "target_query", None)
        if isinstance(q, dict):
            query = q
    except Exception:
        query = {}

    # Use ElementResolver with a single semantic strategy against this catalog
    try:
        if candidates:
            resolver = ElementResolver()
            resolved = resolver.resolve(query, {"candidates": candidates})
            return {
                "candidates": candidates,
                **resolved,
            }
    except Exception:
        pass
    # No candidates or resolution failed; return basic payload
    return {
        "candidates": candidates,
        "primary": None,
        "fallbacks": [],
        "confidence": 0.0,
        "reason": "no-candidates" if not candidates else "unresolved",
    }
