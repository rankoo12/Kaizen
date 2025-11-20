from engine.core.pagebrain.pagebrain_resolver import PageBrainResolver
from engine.core.pagebrain.model_store import PageBrainModelStore


class FakeResolver(PageBrainResolver):
    def __init__(self):
        store = PageBrainModelStore(default_model_id="global-model")
        store.register_model("global-model", {"path": "global.pb"})
        store.set_model("tenant-1", "tenant-model")
        store.register_model("tenant-model", {"path": "tenant.pb"})
        super().__init__(browser=None, model_store=store)

    def resolve(self, query, snapshot):
        # Provide deterministic candidates
        cand = {"type": "css", "value": "#login", "visible": True, "enabled": True}
        return {"primary": cand, "fallbacks": [], "confidence": 1.0, "reason": "test", "bbox": None}


def test_pagebrain_resolver_records_tenant_model():
    resolver = FakeResolver()
    resolver.set_tenant("tenant-1")
    out = resolver.find({"text": "Login"})
    assert isinstance(out, list) and out
    meta = resolver.get_last_pagebrain()
    assert meta["model_id"] == "tenant-model"
    assert isinstance(meta["model_info"], dict)
    assert meta["model_info"]["id"] == "tenant-model"
    assert meta["model_info"]["loaded"] is True
