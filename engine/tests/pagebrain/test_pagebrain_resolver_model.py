from engine.core.pagebrain.pagebrain_resolver import PageBrainResolver
from engine.core.pagebrain.model_store import PageBrainModelStore


class StaticResolver(PageBrainResolver):
    def __init__(self):
        store = PageBrainModelStore(default_model_id="weights-model")
        store.register_model("weights-model", {"weights": {"rank": -1.0, "has_id": 2.0}})
        super().__init__(browser=None, model_store=store)

    def _resolve_candidates(self, target):
        return [
            {"type": "css", "value": ".btn", "visible": True, "enabled": True},
            {"type": "css", "value": "#primary", "visible": True, "enabled": True},
        ]


def test_pagebrain_resolver_uses_model_weights():
    resolver = StaticResolver()
    out = resolver.find({"text": "Click Primary"})
    assert isinstance(out, list) and out
    # With weights favoring has_id, second candidate should come first
    assert out[0]["value"] == "#primary"
    meta = resolver.get_last_pagebrain()
    assert meta["chosen"]["selector"]["value"] == "#primary"
