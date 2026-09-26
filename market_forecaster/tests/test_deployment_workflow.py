from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "master_marketforecaster.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_production_deploy_enforces_core_feature_flags():
    text = _workflow_text()

    for setting in (
        "DEMO_MODE_ENABLED=true",
        "MULTI_USER_ENABLED=true",
        "DATABASE_PERSISTENCE_ENABLED=true",
        "SHARED_CONTRACT_STORAGE_ENABLED=true",
        "SHARED_AUTHORITY_ENABLED=true",
    ):
        assert setting in text


def test_production_deploy_checks_persistent_session_dependencies():
    text = _workflow_text()

    assert "Validate Azure production configuration" in text
    assert 'require_setting "MARKET_FORECASTER_SUPABASE_URL"' in text
    assert 'require_setting "MARKET_FORECASTER_SUPABASE_PUBLISHABLE_KEY"' in text
    assert 'require_setting "MARKET_FORECASTER_SUPABASE_SERVICE_ROLE_KEY"' in text
    assert "Required Azure App Service setting" in text


def test_billing_settings_are_required_only_when_subscriptions_enabled():
    text = _workflow_text()

    assert "SUBSCRIPTIONS_ENABLED" in text
    assert 'require_setting "MARKET_FORECASTER_PUBLIC_URL"' in text
    assert 'require_setting "STRIPE_SECRET_KEY"' in text
    assert 'require_setting "STRIPE_STANDARD_PRICE_ID"' in text
    assert 'require_setting "STRIPE_PRO_PRICE_ID"' in text
    assert "Subscriptions are not enabled; Stripe settings remain non-blocking" in text


def test_deployment_preflight_does_not_print_setting_values():
    text = _workflow_text()

    # The preflight intentionally logs setting names only. Keep the Azure-returned
    # value inside the shell variable used for the empty-value check.
    assert 'echo "$value"' not in text
    assert "Intentionally print only the setting name, never the value." in text
