from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "provision_azure_monitor_alerts.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_alert_workflow_validates_on_push_but_only_applies_manually():
    text = _text()

    assert "push:" in text
    assert "workflow_dispatch:" in text
    assert "inputs:" in text
    assert "apply:" in text
    assert "Create or update Azure Monitor alerts" in text
    assert "if: github.event_name == 'workflow_dispatch' && inputs.apply" in text


def test_alert_workflow_requires_notification_email_only_for_apply():
    text = _text()

    assert "MARKET_FORECASTER_AZURE_ALERT_EMAIL" in text
    assert 'echo "::add-mask::$ALERT_EMAIL"' in text
    assert "Repository secret MARKET_FORECASTER_AZURE_ALERT_EMAIL is required" in text


def test_alert_workflow_validates_expected_app_service_metrics():
    text = _text()

    for metric in (
        "Http5xx",
        "HttpResponseTime",
        "CpuPercentage",
        "MemoryPercentage",
    ):
        assert metric in text


def test_alert_workflow_defines_core_alerts_and_thresholds():
    text = _text()

    expected_alerts = (
        "marketforecaster-ui-5xx",
        "marketforecaster-api-5xx",
        "marketforecaster-ui-latency",
        "marketforecaster-api-latency",
        "marketforecaster-plan-cpu",
        "marketforecaster-plan-memory",
    )
    for alert in expected_alerts:
        assert alert in text

    assert "total Http5xx > 5" in text
    assert "total Http5xx > 3" in text
    assert "avg HttpResponseTime > 5" in text
    assert "avg HttpResponseTime > 3" in text
    assert "avg CpuPercentage > 85" in text
    assert "avg MemoryPercentage > 85" in text


def test_alert_workflow_uses_existing_azure_oidc_connection():
    text = _text()

    assert "azure/login@v2" in text
    assert "AZUREAPPSERVICE_CLIENTID_" in text
    assert "AZUREAPPSERVICE_TENANTID_" in text
    assert "AZUREAPPSERVICE_SUBSCRIPTIONID_" in text
