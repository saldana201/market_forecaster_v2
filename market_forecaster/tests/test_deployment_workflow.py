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
        "MARKET_FORECASTER_API_PUBLIC_URL=https://marketforecaster-api.azurewebsites.net",
        "MARKET_FORECASTER_PRO_API_MONTHLY_REQUESTS=1000",
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
    assert 'require_setting "MARKET_FORECASTER_BILLING_MODE"' in text
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



def test_billing_preflight_enforces_test_live_secret_boundaries():
    text = _workflow_text()

    assert "Test billing mode requires an sk_test_ Stripe secret key." in text
    assert "Live billing mode requires an sk_live_ Stripe secret key." in text
    assert "Live billing mode requires an HTTPS public return URL." in text
    assert "MARKET_FORECASTER_BILLING_MODE must be test or live." in text
    assert "unset stripe_secret" in text



def test_production_deploy_runs_strict_billing_readiness():
    text = _workflow_text()

    assert "Validate deployed launch readiness" in text
    assert "Run strict production readiness gate" in text
    assert "python -m market_forecaster.scripts.production_readiness" in text
    assert "--strict" in text
    assert "--require-billing" in text
    assert "stripe_price_catalog" in text
    assert "pro_api_usage_metering" in text


def test_production_deploy_masks_runtime_secrets_before_readiness():
    text = _workflow_text()

    assert 'echo "::add-mask::$value"' in text
    assert "MARKET_FORECASTER_SUPABASE_SERVICE_ROLE_KEY|STRIPE_SECRET_KEY" in text
    assert 'printf \'%s=%s\\n\' "$name" "$value" >> "$GITHUB_ENV"' in text


def test_production_deploy_verifies_dedicated_api_quota_restored():
    text = _workflow_text()

    assert "Verify dedicated Pro API after UI deployment" in text
    assert "marketforecaster-api.azurewebsites.net/api/v1/ready" in text
    assert "monthly_request_limit" in text
    assert "Dedicated Pro API monthly quota is not restored to 1000" in text


def test_production_deploy_uploads_readiness_artifacts():
    text = _workflow_text()

    assert "marketforecaster-production-readiness-" in text
    assert "production-readiness.json" in text
    assert "pro-api-ready.json" in text
