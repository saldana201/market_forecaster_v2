from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "monitor_marketforecaster_production.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_production_monitor_runs_hourly_and_manually():
    text = _text()

    assert "schedule:" in text
    assert "cron: '17 * * * *'" in text
    assert "workflow_dispatch:" in text
    assert "timeout-minutes: 5" in text


def test_production_monitor_checks_public_ui_and_api_without_customer_secret():
    text = _text()

    assert "https://marketforecaster.oneeightaisystems.com/" in text
    assert "https://marketforecaster-api.azurewebsites.net" in text
    assert "/api/v1/health" in text
    assert "/api/v1/ready" in text
    assert "X-API-Key" not in text
    assert "MARKET_FORECASTER_API_KEY" not in text
    assert "SUPABASE_SERVICE_ROLE_KEY" not in text


def test_production_monitor_validates_commercial_api_dependencies():
    text = _text()

    assert "pro_customer_api_keys" in text
    assert "pro_api_usage_metering" in text
    assert "monthly_request_limit" in text
    assert "expected 1000" in text
    assert "shared_api_rate_limit" in text


def test_production_monitor_retains_failure_diagnostics():
    text = _text()

    assert "Upload failure diagnostics" in text
    assert "api-health.json" in text
    assert "api-ready.json" in text
    assert "retention-days: 7" in text
