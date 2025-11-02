from typing import Protocol, Optional, Dict, Any
from ..types.dtos import LocatorCandidates


class ISelectorHealer(Protocol):
    """Attempt to recover from a failed locator resolution/interaction."""

    def heal(self, failure: dict, context: dict) -> Optional[LocatorCandidates]: ...


class DeterministicHealer:
    """Minimal deterministic healer heuristics.

    - Prefer stable attributes (testid/id/class) when present in the target.
    - Generalize CSS by stripping combinators/pseudo-selectors.
    - If only text is available, fallback to a naive text-oriented CSS.

    Returned structure matches LocatorCandidates with just a primary.
    """

    def __init__(self, storage: Any | None = None) -> None:
        self._storage = storage

    def heal(self, failure: Dict[str, Any], context: Dict[str, Any]) -> Optional[LocatorCandidates]:
        # 0) Profile-assisted selector (if available)
        try:
            if self._storage is not None:
                find = getattr(self._storage, "find_locator_profile", None)
                if callable(find):
                    prof = find(domain=None, tool=str(context.get("tool", "")), target_signature=failure.get("target") or {})
                    if isinstance(prof, dict) and prof.get("type") and prof.get("value"):
                        return {
                            "primary": {"type": prof.get("type"), "value": prof.get("value"), "visible": True, "enabled": True},
                            "fallbacks": [],
                            "confidence": 0.7,
                            "reason": "profile_hit",
                        }
        except Exception:
            pass
        target = failure.get("target") or {}
        # 1) Direct CSS provided → generalize
        css = target.get("css")
        if isinstance(css, str) and css:
            gen = self._generalize_css(css)
            return {
                "primary": {"type": "css", "value": gen, "visible": True, "enabled": True},
                "fallbacks": [],
                "confidence": 0.5,
                "reason": "generalized_css",
            }
        # 2) Use stable attributes if present
        for key, prefix in (("testid", "[data-testid='"), ("id", "#")):
            v = target.get(key)
            if isinstance(v, str) and v:
                sel = f"{prefix}{v}']" if key == "testid" else f"#{v}"
                return {
                    "primary": {"type": "css", "value": sel, "visible": True, "enabled": True},
                    "fallbacks": [],
                    "confidence": 0.6,
                    "reason": f"stable_{key}",
                }
        # 3) Text fallback (weak)
        text = target.get("text")
        if isinstance(text, str) and text:
            # naive contains selector; real impl should use resolver
            sel = f"*:contains('{text}')"
            return {
                "primary": {"type": "css", "value": sel, "visible": True, "enabled": True},
                "fallbacks": [],
                "confidence": 0.2,
                "reason": "text_fallback",
            }
        return None

    def _generalize_css(self, css: str) -> str:
        # Strip combinators and pseudo selectors to get a stable anchor
        base = css.split(" ")[0].split(">")[0].split(":")[0]
        return base or css
