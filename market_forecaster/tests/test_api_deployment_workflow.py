from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy_marketforecaster_api.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_api_deploy_is_manual_only():
    text = _workflow_text()

    assert "workflow_dispatch:" in text
    assert "\n  push:" not in text


def test_api_deploy_uses_fastapi_uvicorn_runtime():
    text = _workflow_text()

    assert "python -m uvicorn market_forecaster.api.main:app" in text
    assert "--port 8000" in text
    assert "PYTHON|3.12" in text


def test_api_deploy_requires_existing_app_and_server_secrets():
    text = _workflow_text()

    assert "does not exist. Provision the dedicated API App Service first." in text
    for setting in (
        "MARKET_FORECASTER_ENV",
        "MARKET_FORECASTER_API_KEY",
        "MARKET_FORECASTER_ALLOWED_ORIGINS",
        "MARKET_FORECASTER_SUPABASE_URL",
        "MARKET_FORECASTER_SUPABASE_SERVICE_ROLE_KEY",
        "MARKET_FORECASTER_PRO_API_MONTHLY_REQUESTS",
        "SUBSCRIPTIONS_ENABLED",
    ):
        assert f"require_setting {setting}" in text


def test_api_deploy_fails_closed_without_pro_subscription_authority():
    text = _workflow_text()

    assert "MARKET_FORECASTER_ENV must be production" in text
    assert "SUBSCRIPTIONS_ENABLED must be true" in text


def test_api_deploy_verifies_health_readiness_and_customer_key_config():
    text = _workflow_text()

    assert "/api/v1/health" in text
    assert "/api/v1/ready" in text
    assert "pro_customer_api_keys" in text
    assert "pro_api_usage_metering" in text
    assert "usage metering are configured" in text



def test_api_deploy_requires_positive_monthly_customer_quota():
    text = _workflow_text()

    assert "MARKET_FORECASTER_PRO_API_MONTHLY_REQUESTS must be a positive integer." in text
    assert "Configured monthly Pro API quota" in text



def test_api_deploy_publishes_dedicated_host_to_streamlit_ui():
    text = _workflow_text()

    assert "Publish API hostname to Streamlit UI" in text
    assert 'UI_APP="marketforecaster"' in text
    assert 'MARKET_FORECASTER_API_PUBLIC_URL="https://$APP_HOST"' in text
    assert "MARKET_FORECASTER_PRO_API_MONTHLY_REQUESTS=1000" in text
