from engine.core.config.settings import Settings


def test_env_allowed_url_schemes_parsing(monkeypatch):
    monkeypatch.setenv("KAIZEN_ALLOWED_URL_SCHEMES", "data:,about:blank,file:")
    s = Settings()
    assert s.ALLOWED_URL_SCHEMES == ["data:", "about:blank", "file:"]
