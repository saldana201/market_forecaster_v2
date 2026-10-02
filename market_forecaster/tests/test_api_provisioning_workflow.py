from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "provision_marketforecaster_api.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_api_provisioning_reuses_existing_app_service_plan():
    text = _text()

    assert "serverFarmId" in text
    assert "PLAN_NAME" in text
    assert "az webapp create" in text
    assert '--plan "$PLAN_NAME"' in text
    assert "az appservice plan create" not in text


def test_api_provisioning_is_idempotent():
    text = _text()

    assert "[?name=='$TARGET_APP'].name | [0]" in text
    assert "marketforecaster-api" in text


def test_api_provisioning_configures_non_secret_commercial_settings():
    text = _text()

    for setting in (
        "MARKET_FORECASTER_ENV=production",
        "MARKET_FORECASTER_ALLOWED_ORIGINS=https://marketforecaster.oneeightaisystems.com",
        "MARKET_FORECASTER_SUPABASE_URL=https://pbttpkbkimqdoilmwryi.supabase.co",
        "SUBSCRIPTIONS_ENABLED=true",
        "MARKET_FORECASTER_PRO_API_MONTHLY_REQUESTS=1000",
        "MARKET_FORECASTER_SHARED_RATE_LIMIT_ENABLED=true",
        "MARKET_FORECASTER_RATE_LIMIT_REQUESTS=30",
        "MARKET_FORECASTER_RATE_LIMIT_WINDOW_SECONDS=60",
    ):
        assert setting in text


def test_api_provisioning_does_not_embed_server_secrets():
    text = _text()

    assert "MARKET_FORECASTER_SUPABASE_SERVICE_ROLE_KEY=" not in text
    assert "MARKET_FORECASTER_API_KEY=" not in text
    assert "MARKET_FORECASTER_RATE_LIMIT_HASH_SECRET=" not in text
    assert "Before deployment, configure these required server-only settings" in text
    assert "Optional hardening:" in text


def test_api_provisioning_sets_fastapi_runtime():
    text = _text()

    assert "PYTHON:3.12" in text
    assert "python -m uvicorn market_forecaster.api.main:app" in text
    assert "--port 8000" in text
