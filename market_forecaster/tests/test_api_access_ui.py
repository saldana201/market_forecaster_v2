from market_forecaster.ui import api_access


def test_api_public_url_is_explicit_and_normalized(monkeypatch):
    monkeypatch.setenv(
        "MARKET_FORECASTER_API_PUBLIC_URL",
        "https://api.marketforecaster.example/",
    )

    assert (
        api_access._api_public_url()
        == "https://api.marketforecaster.example"
    )


def test_api_public_url_has_no_implicit_ui_host_fallback(monkeypatch):
    monkeypatch.delenv("MARKET_FORECASTER_API_PUBLIC_URL", raising=False)

    assert api_access._api_public_url() == ""



def test_api_monthly_limit_defaults_to_initial_launch_allowance(monkeypatch):
    monkeypatch.delenv(
        "MARKET_FORECASTER_PRO_API_MONTHLY_REQUESTS",
        raising=False,
    )

    assert api_access._pro_api_monthly_limit() == 1000


def test_api_monthly_limit_is_environment_configurable(monkeypatch):
    monkeypatch.setenv(
        "MARKET_FORECASTER_PRO_API_MONTHLY_REQUESTS",
        "2500",
    )

    assert api_access._pro_api_monthly_limit() == 2500



def test_customer_api_connection_test_calls_usage_endpoint(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"monthly_limit":1000,"used":1,"remaining":999,"period_start":"2026-10-01","period_end":"2026-11-01"}'

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["api_key"] = req.headers.get("X-api-key")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(api_access.request, "urlopen", fake_urlopen)

    result = api_access._test_customer_api_key(
        "https://marketforecaster-api.azurewebsites.net/",
        "mfk_test_secret",
    )

    assert captured["url"].endswith("/api/v1/api/usage")
    assert captured["api_key"] == "mfk_test_secret"
    assert result["used"] == 1
    assert result["remaining"] == 999


def test_customer_api_connection_test_requires_published_host():
    try:
        api_access._test_customer_api_key("", "mfk_test_secret")
    except Exception as exc:
        assert "hostname" in str(exc).lower()
    else:
        raise AssertionError("Expected missing API host to fail")
