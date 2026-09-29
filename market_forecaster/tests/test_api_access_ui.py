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
