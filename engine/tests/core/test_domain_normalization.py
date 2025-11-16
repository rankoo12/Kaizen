from engine.core.net.domains import normalize_registrable_domain


def test_normalize_basic_domains():
    assert normalize_registrable_domain("example.com") == "example.com"
    assert normalize_registrable_domain("Sub.Example.COM") == "example.com"


def test_normalize_sld_buckets():
    # co.uk keeps example.co.uk; subdomains collapse to eTLD+1
    assert normalize_registrable_domain("example.co.uk") == "example.co.uk"
    assert normalize_registrable_domain("app.example.co.uk") == "example.co.uk"
    # com.au
    assert normalize_registrable_domain("shop.example.com.au") == "example.com.au"


def test_normalize_ips_and_localhost():
    assert normalize_registrable_domain("127.0.0.1") == "127.0.0.1"
    assert normalize_registrable_domain("localhost") == "localhost"
