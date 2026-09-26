from __future__ import annotations

import json

from market_forecaster.billing.stripe_client import StripeBillingClient
from market_forecaster.core.session_identity import AppIdentity
import market_forecaster.services.subscriptions as subscriptions
from market_forecaster.services.subscriptions import (
    effective_plan,
    normalize_requested_plan,
    requested_plan_is_satisfied,
    subscription_configuration_diagnostics,
)


def test_effective_plan_requires_entitled_status():
    assert effective_plan(None) == ("demo", "none")
    assert effective_plan({"plan": "standard", "status": "active"}) == (
        "standard",
        "active",
    )
    assert effective_plan({"plan": "pro", "status": "trialing"}) == (
        "pro",
        "trialing",
    )
    assert effective_plan({"plan": "pro", "status": "past_due"}) == (
        "pro",
        "past_due",
    )
    assert effective_plan({"plan": "pro", "status": "canceled"}) == (
        "demo",
        "canceled",
    )
    assert effective_plan({"plan": "standard", "status": "unpaid"}) == (
        "demo",
        "unpaid",
    )


def test_checkout_session_carries_verified_user_and_plan_metadata(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "id": "cs_test_123",
                    "url": "https://checkout.stripe.com/test",
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["body"] = req.data.decode("utf-8")
        captured["authorization"] = req.headers["Authorization"]
        return FakeResponse()

    monkeypatch.setattr(
        "market_forecaster.billing.stripe_client.request.urlopen",
        fake_urlopen,
    )

    client = StripeBillingClient("sk_test_example")
    result = client.create_checkout_session(
        user_id="11111111-1111-4111-8111-111111111111",
        email="user@example.com",
        plan="pro",
        price_id="price_pro",
        success_url="https://example.com/?billing=success",
        cancel_url="https://example.com/?billing=cancel",
    )

    assert result["url"].startswith("https://checkout.stripe.com/")
    assert captured["url"].endswith("/v1/checkout/sessions")
    assert captured["authorization"] == "Bearer sk_test_example"
    assert "mode=subscription" in captured["body"]
    assert "client_reference_id=11111111-1111-4111-8111-111111111111" in captured["body"]
    assert "metadata%5Bplan%5D=pro" in captured["body"]
    assert "subscription_data%5Bmetadata%5D%5Buser_id%5D=" in captured["body"]
    assert "line_items%5B0%5D%5Bprice%5D=price_pro" in captured["body"]



def _identity(plan: str, status: str) -> AppIdentity:
    return AppIdentity(
        user_id="internal-user",
        session_id="session",
        authenticated=True,
        plan=plan,
        subscription_status=status,
        is_admin=False,
        auth_provider="supabase",
        auth_subject="11111111-1111-4111-8111-111111111111",
    )


def test_requested_plan_normalization_and_satisfaction():
    assert normalize_requested_plan("STANDARD") == "standard"
    assert normalize_requested_plan(" pro ") == "pro"
    assert normalize_requested_plan("demo") is None
    assert normalize_requested_plan("anything") is None

    assert requested_plan_is_satisfied(_identity("standard", "active"), "standard") is True
    assert requested_plan_is_satisfied(_identity("pro", "active"), "standard") is True
    assert requested_plan_is_satisfied(_identity("standard", "active"), "pro") is False
    assert requested_plan_is_satisfied(_identity("pro", "canceled"), "pro") is False
    assert requested_plan_is_satisfied(_identity("demo", "none"), None) is True


def test_subscription_diagnostics_are_secret_safe(monkeypatch):
    monkeypatch.setattr(subscriptions, "SUBSCRIPTIONS_ENABLED", True)
    monkeypatch.setattr(subscriptions, "DATABASE_PERSISTENCE_ENABLED", True)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_do-not-expose-this-value")
    monkeypatch.setenv("STRIPE_STANDARD_PRICE_ID", "price_standard")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro")
    monkeypatch.setenv(
        "MARKET_FORECASTER_PUBLIC_URL",
        "https://marketforecaster.oneeightaisystems.com",
    )

    rows = subscription_configuration_diagnostics()
    by_name = {row["name"]: row for row in rows}

    assert by_name["Subscription feature flag"]["ready"] is True
    assert by_name["Persistent account storage"]["ready"] is True
    assert by_name["Stripe secret key"]["detail"] == "test"
    assert "do-not-expose" not in str(rows)
    assert by_name["Standard recurring price"]["ready"] is True
    assert by_name["Pro recurring price"]["ready"] is True


def test_subscription_diagnostics_identify_missing_activation_pieces(monkeypatch):
    monkeypatch.setattr(subscriptions, "SUBSCRIPTIONS_ENABLED", False)
    monkeypatch.setattr(subscriptions, "DATABASE_PERSISTENCE_ENABLED", True)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_STANDARD_PRICE_ID", raising=False)
    monkeypatch.delenv("STRIPE_PRO_PRICE_ID", raising=False)

    rows = subscription_configuration_diagnostics()
    by_name = {row["name"]: row for row in rows}

    assert by_name["Subscription feature flag"]["ready"] is False
    assert by_name["Stripe secret key"]["ready"] is False
    assert by_name["Standard recurring price"]["ready"] is False
    assert by_name["Pro recurring price"]["ready"] is False
