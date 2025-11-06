from engine.core.resolving.element_resolver import ElementResolver


def test_find_heal_zero_returns_empty():
    r = ElementResolver()
    assert r.find({"text": "[heal-zero]"}) == []


def test_find_heal_multi_returns_two():
    r = ElementResolver()
    out = r.find({"text": "[heal-multi]"})
    assert isinstance(out, list) and len(out) == 2


def test_find_heal_hidden_returns_not_visible():
    r = ElementResolver()
    out = r.find({"text": "[heal-hidden]"})
    assert len(out) == 1 and out[0].get("visible") is False
