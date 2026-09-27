from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WEBHOOK = ROOT / "supabase" / "functions" / "stripe-webhook" / "index.ts"
MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260927091000_subscription_webhook_ordering.sql"
)


def test_subscription_event_rpc_rejects_older_events():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "stripe_event_created_at" in sql
    assert "apply_market_forecaster_subscription_event" in sql
    assert (
        "excluded.stripe_event_created_at >= "
        "public.subscriptions.stripe_event_created_at"
    ) in sql
    assert "grant execute" in sql
    assert "to service_role" in sql
    assert "from public, anon, authenticated" in sql


def test_checkout_completion_does_not_downgrade_existing_subscription_status():
    source = WEBHOOK.read_text(encoding="utf-8")

    assert 'select("status")' in source
    assert 'currentStatus === "none" ? "incomplete" : currentStatus' in source
    assert 'const checkoutStatus =' in source
    assert 'status: checkoutStatus' in source


def test_subscription_events_use_atomic_ordering_rpc():
    source = WEBHOOK.read_text(encoding="utf-8")

    assert 'supabase.rpc(' in source
    assert '"apply_market_forecaster_subscription_event"' in source
    assert "p_stripe_event_id" in source
    assert "p_stripe_event_created_at" in source
    assert "ignored_stale_event" in source


def test_webhook_requires_paid_plan_metadata_or_existing_paid_plan():
    source = WEBHOOK.read_text(encoding="utf-8")

    assert "PAID_PLANS" in source
    assert "Missing or invalid checkout plan metadata" in source
    assert "Missing or invalid subscription plan metadata" in source
