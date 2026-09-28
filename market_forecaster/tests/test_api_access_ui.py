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
