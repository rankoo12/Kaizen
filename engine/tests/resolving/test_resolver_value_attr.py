from engine.core.resolving.element_resolver import ElementResolver


class EvalBrowser:
    """Minimal browser stub exposing run_coro + evaluate for resolver.find()."""

    def run_coro(self, value):
        # resolver calls runner(eval_fn(script)); our eval_fn returns plain value
        return value

    async def open(self, url: str):
        pass

    def evaluate(self, script: str):
        s = str(script).lower()
        # Pretend only selectors that include input[value*="small" i] exist
        return ("input[value*" in s) and ("small" in s)


def test_find_text_prefers_input_value_contains_when_present():
    r = ElementResolver(browser=EvalBrowser())
    out = r.find({"text": "small size"})
    assert isinstance(out, list) and len(out) >= 1
    sel = out[0]
    assert isinstance(sel, dict) and sel.get("type") == "css"
    val = sel.get("value") or ""
    assert 'input[value*="small" i]' in val
