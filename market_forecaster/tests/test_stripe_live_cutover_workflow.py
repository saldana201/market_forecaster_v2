from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LIVE_WORKFLOW = ROOT / ".github" / "workflows" / "validate_stripe_live_cutover.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _live_text() -> str:
    return LIVE_WORKFLOW.read_text(encoding="utf-8")


def _ci_text() -> str:
    return CI_WORKFLOW.read_text(encoding="utf-8")


def test_live_stripe_validation_is_manual_and_no_charge():
    text = _live_text()

    assert "workflow_dispatch:" in text
    assert "Validate Stripe live cutover" in text
    assert "does not create a charge" in text.lower()
    assert "checkout.session" not in text.lower()


def test_live_stripe_validation_requires_live_mode_and_live_secret():
    text = _live_text()

    assert "MARKET_FORECASTER_BILLING_MODE must be live" in text
    assert "sk_live_*" in text
    assert "SUBSCRIPTIONS_ENABLED must be true" in text
    assert "Live billing requires an HTTPS public URL" in text


def test_live_stripe_validation_runs_strict_catalog_readiness():
    text = _live_text()

    assert "production_readiness" in text
    assert "--strict" in text
    assert "--require-billing" in text
    assert "stripe_subscriptions" in text
    assert "stripe_price_catalog" in text


def test_live_stripe_validation_masks_sensitive_settings():
    text = _live_text()

    assert "MARKET_FORECASTER_SUPABASE_SERVICE_ROLE_KEY|STRIPE_SECRET_KEY" in text
    assert 'echo "::add-mask::$value"' in text


def test_container_ci_retries_transient_registry_failures():
    text = _ci_text()

    assert "for attempt in 1 2 3" in text
    assert "Container build attempt $attempt failed" in text
    assert "API container build failed after 3 attempts" in text
