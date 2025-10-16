from fastapi.testclient import TestClient
from engine.api.server import create_app


class FakeResolver:
    def resolve(self, query, snapshot):
        return {
            "primary": {"type": "css", "value": "#login"},
            "fallbacks": [{"type": "role", "value": "button"}],
            "confidence": 0.92,
            "reason": "matched text≈query.text",
            "bbox": {"x": 10, "y": 20, "w": 100, "h": 40},
        }


def test_resolve_ok_200():
    # Contract test: inject a fake so we test only routing + schema + response shape
    app = create_app(resolver=FakeResolver())
    client = TestClient(app)

    body = {
        "snapshot": {
            "html_path": "tests/fixtures/smoke.html",
            "candidates": [],  # OK: fake doesn’t need a catalog
            "styles_index_path": None,
            "screenshot_path": None,
            "frames": [],
        },
        "query": {
            "text": "login",
            "hints": {"role": "button", "color": "blue", "near": "header"},
            "scope": None,
        },
    }
    res = client.post("/api/resolve", json=body)
    assert res.status_code == 200, res.text
    data = res.json()
    # Minimal shape assertions to match LocatorCandidates
    assert "primary" in data and "confidence" in data and "reason" in data


def test_resolve_schema_422_on_missing_fields():
    # Missing "query" => JSON-schema 422 from the route
    app = create_app(resolver=FakeResolver())
    client = TestClient(app)

    bad = {"snapshot": {"html_path": "x", "candidates": []}}  # missing "query"
    res = client.post("/api/resolve", json=bad)
    assert res.status_code == 422
    assert "Schema validation failed" in res.text


def test_resolver_500_on_exception():
    class BoomResolver:
        def resolve(self, query, snapshot):
            raise RuntimeError("planned boom")

    # Contract test: inject a resolver that throws to verify 500 mapping
    app = create_app(resolver=BoomResolver())
    client = TestClient(app)

    body = {
        "snapshot": {
            "html_path": "x",
            "candidates": [],
            "styles_index_path": None,
            "screenshot_path": None,
            "frames": [],
        },
        "query": {
            "text": "anything",
            "hints": {"role": "button", "color": "red", "near": "logo"},
            "scope": None,
        },
    }
    res = client.post("/api/resolve", json=body)
    assert res.status_code == 500
    assert "resolver error" in res.text
