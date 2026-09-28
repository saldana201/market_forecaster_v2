"""Subscription authority and Stripe checkout orchestration."""
from __future__ import annotations

import os
from dataclasses import replace
from typing import MutableMapping

from market_forecaster.auth.session import AUTH_PROFILE_KEY
from market_forecaster.billing.stripe_client import BillingError, StripeBillingClient
from market_forecaster.config import DATABASE_PERSISTENCE_ENABLED, SUBSCRIPTIONS_ENABLED
from market_forecaster.core.session_identity import IDENTITY_SESSION_KEY, AppIdentity
from market_forecaster.persistence.supabase_data import PersistenceError
from market_forecaster.services.user_data import client_for_state, verified_owner_id


ENTITLED_STATUSES = {"trialing", "active", "past_due"}
PAID_PLANS = {"standard", "pro"}
PLAN_RANK = {"demo": 0, "standard": 1, "pro": 2}
BILLING_MODES = {"test", "live"}


def billing_mode() -> str:
    return str(os.getenv("MARKET_FORECASTER_BILLING_MODE", "test") or "test").strip().lower()


def _public_url() -> str:
    return str(
        os.getenv(
            "MARKET_FORECASTER_PUBLIC_URL",
            "https://marketforecaster.oneeightaisystems.com",
        )
    ).strip().rstrip("/")


def _stripe_secret() -> str:
    return str(os.getenv("STRIPE_SECRET_KEY") or "").strip()


def _price_id(plan: str) -> str:
    key = {
        "standard": "STRIPE_STANDARD_PRICE_ID",
        "pro": "STRIPE_PRO_PRICE_ID",
    }.get(plan)
    return str(os.getenv(key or "") or "").strip()


def subscription_configuration_diagnostics() -> list[dict]:
    """Return a secret-safe checklist for subscription activation."""
    secret = _stripe_secret()
    mode = billing_mode()
    if secret.startswith("sk_test_"):
        stripe_mode = "test"
    elif secret.startswith("sk_live_"):
        stripe_mode = "live"
    elif secret:
        stripe_mode = "configured"
    else:
        stripe_mode = "missing"

    mode_valid = mode in BILLING_MODES
    secret_matches_mode = bool(secret) and mode_valid and stripe_mode == mode
    public_url = _public_url()
    public_url_ready = bool(public_url) and (
        mode != "live" or public_url.startswith("https://")
    )

    return [
        {
            "name": "Billing mode",
            "ready": mode_valid,
            "detail": mode if mode_valid else "invalid",
        },
        {
            "name": "Subscription feature flag",
            "ready": bool(SUBSCRIPTIONS_ENABLED),
            "detail": "enabled" if SUBSCRIPTIONS_ENABLED else "disabled",
        },
        {
            "name": "Persistent account storage",
            "ready": bool(DATABASE_PERSISTENCE_ENABLED),
            "detail": "enabled" if DATABASE_PERSISTENCE_ENABLED else "disabled",
        },
        {
            "name": "Stripe secret key",
            "ready": secret_matches_mode,
            "detail": (
                stripe_mode
                if secret_matches_mode
                else "missing"
                if not secret
                else f"{stripe_mode} key does not match {mode or 'configured'} mode"
            ),
        },
        {
            "name": "Standard recurring price",
            "ready": bool(_price_id("standard")),
            "detail": "configured" if _price_id("standard") else "missing",
        },
        {
            "name": "Pro recurring price",
            "ready": bool(_price_id("pro")),
            "detail": "configured" if _price_id("pro") else "missing",
        },
        {
            "name": "Public return URL",
            "ready": public_url_ready,
            "detail": (
                public_url
                if public_url_ready
                else "missing"
                if not public_url
                else "live billing requires an https:// public URL"
            ),
        },
    ]


def subscription_configuration_status() -> tuple[bool, str]:
    checks = subscription_configuration_diagnostics()
    first_missing = next((row for row in checks if not row["ready"]), None)
    if first_missing is None:
        return True, "ready"

    name = str(first_missing["name"])
    detail = str(first_missing["detail"])
    if name == "Billing mode":
        return False, "MARKET_FORECASTER_BILLING_MODE must be test or live."
    if name == "Subscription feature flag":
        return False, "SUBSCRIPTIONS_ENABLED is false."
    if name == "Persistent account storage":
        return False, "DATABASE_PERSISTENCE_ENABLED must be enabled first."
    if name == "Stripe secret key":
        if not _stripe_secret():
            return False, "STRIPE_SECRET_KEY is not configured."
        return False, "Stripe secret key does not match MARKET_FORECASTER_BILLING_MODE."
    if name in {"Standard recurring price", "Pro recurring price"}:
        return False, "Stripe Standard or Pro price ID is not configured."
    return False, f"{name} is not ready ({detail})."


def stripe_catalog_diagnostics() -> list[dict]:
    """Validate configured Stripe recurring prices without creating a charge."""
    secret = _stripe_secret()
    mode = billing_mode()
    if not secret:
        return [
            {
                "plan": plan,
                "ready": False,
                "detail": "Stripe secret key is missing.",
            }
            for plan in sorted(PAID_PLANS)
        ]
    if mode not in BILLING_MODES:
        return [
            {
                "plan": plan,
                "ready": False,
                "detail": "Billing mode is invalid.",
            }
            for plan in sorted(PAID_PLANS)
        ]

    client = StripeBillingClient(secret)
    rows: list[dict] = []
    for plan in ("standard", "pro"):
        price_id = _price_id(plan)
        if not price_id:
            rows.append(
                {
                    "plan": plan,
                    "ready": False,
                    "detail": "Price ID is missing.",
                }
            )
            continue

        try:
            price = client.retrieve_price(price_id)
        except BillingError as exc:
            rows.append(
                {
                    "plan": plan,
                    "ready": False,
                    "detail": str(exc),
                }
            )
            continue

        livemode = bool(price.get("livemode"))
        expected_livemode = mode == "live"
        active = bool(price.get("active"))
        recurring = price.get("recurring")
        price_type = str(price.get("type") or "")
        interval = (
            str(recurring.get("interval") or "")
            if isinstance(recurring, dict)
            else ""
        )
        currency = str(price.get("currency") or "").upper()
        unit_amount = price.get("unit_amount")
        try:
            amount_value = int(unit_amount)
        except Exception:
            amount_value = -1

        ready = (
            livemode == expected_livemode
            and active
            and price_type == "recurring"
            and bool(interval)
            and bool(currency)
            and amount_value > 0
        )

        issues: list[str] = []
        if livemode != expected_livemode:
            issues.append("Stripe price environment does not match billing mode")
        if not active:
            issues.append("price is inactive")
        if price_type != "recurring" or not interval:
            issues.append("price is not recurring")
        if not currency or amount_value <= 0:
            issues.append("price amount/currency is invalid")

        amount_text = (
            f"{currency} {amount_value / 100:.2f}/{interval}"
            if amount_value > 0 and currency and interval
            else "invalid recurring price"
        )
        rows.append(
            {
                "plan": plan,
                "ready": ready,
                "detail": amount_text if ready else "; ".join(issues),
                "price_id": price_id,
                "livemode": livemode,
            }
        )

    return rows


def stripe_catalog_status() -> tuple[bool, str]:
    rows = stripe_catalog_diagnostics()
    failed = [row for row in rows if not row.get("ready")]
    if not failed:
        return True, "ready"
    return False, "; ".join(
        f"{str(row.get('plan') or '').title()}: {row.get('detail')}"
        for row in failed
    )


def load_subscription(
    state: MutableMapping,
    identity: AppIdentity,
) -> dict | None:
    client = client_for_state(state, identity)
    user_id = verified_owner_id(identity)
    rows = client.select(
        "subscriptions",
        filters={"user_id": f"eq.{user_id}"},
        limit=1,
    )
    return rows[0] if rows else None


def normalize_requested_plan(value: object) -> str | None:
    plan = str(value or "").strip().lower()
    return plan if plan in PAID_PLANS else None


def effective_plan(subscription: dict | None) -> tuple[str, str]:
    if not subscription:
        return "demo", "none"
    status = str(subscription.get("status") or "none").lower()
    plan = str(subscription.get("plan") or "demo").lower()
    if status in ENTITLED_STATUSES and plan in PAID_PLANS:
        return plan, status
    return "demo", status


def requested_plan_is_satisfied(identity: AppIdentity, requested_plan: object) -> bool:
    requested = normalize_requested_plan(requested_plan)
    if requested is None:
        return True
    if identity.subscription_status not in ENTITLED_STATUSES:
        return False
    return PLAN_RANK.get(identity.plan, 0) >= PLAN_RANK[requested]


def sync_subscription_identity(
    state: MutableMapping,
    identity: AppIdentity,
) -> AppIdentity:
    if not identity.authenticated or not SUBSCRIPTIONS_ENABLED:
        return identity

    try:
        subscription = load_subscription(state, identity)
    except PersistenceError:
        # Billing authorization fails closed when billing is enabled.
        resolved = replace(identity, plan="demo", subscription_status="unavailable")
        state[IDENTITY_SESSION_KEY] = resolved.to_dict()
        return resolved

    plan, status = effective_plan(subscription)
    resolved = replace(identity, plan=plan, subscription_status=status)
    state[IDENTITY_SESSION_KEY] = resolved.to_dict()
    return resolved


def create_checkout_url(
    state: MutableMapping,
    identity: AppIdentity,
    plan: str,
) -> str:
    ready, reason = subscription_configuration_status()
    if not ready:
        raise BillingError(reason)

    plan = str(plan or "").lower()
    if plan not in PAID_PLANS:
        raise BillingError("Unsupported subscription plan.")

    user_id = verified_owner_id(identity)
    profile = state.get(AUTH_PROFILE_KEY)
    email = profile.get("email") if isinstance(profile, dict) else None

    existing = load_subscription(state, identity)
    existing_status = str((existing or {}).get("status") or "none").lower()
    existing_plan = str((existing or {}).get("plan") or "demo").lower()
    existing_subscription_id = str(
        (existing or {}).get("stripe_subscription_id") or ""
    ).strip()
    existing_customer_id = str(
        (existing or {}).get("stripe_customer_id") or ""
    ).strip()

    if existing_status in ENTITLED_STATUSES and existing_subscription_id:
        if existing_plan == plan:
            raise BillingError(
                f"{plan.title()} is already active on this account."
            )
        raise BillingError(
            f"An active {existing_plan.title()} subscription already exists. "
            "Use the Stripe billing portal to change plans so Market Forecaster "
            "does not create a second recurring subscription."
        )

    result = StripeBillingClient(_stripe_secret()).create_checkout_session(
        user_id=user_id,
        email=email,
        customer_id=existing_customer_id or None,
        plan=plan,
        price_id=_price_id(plan),
        success_url=f"{_public_url()}/?billing=success",
        cancel_url=f"{_public_url()}/?billing=cancel",
    )
    url = str(result.get("url") or "").strip()
    if not url:
        raise BillingError("Stripe Checkout did not return a checkout URL.")
    return url


def create_portal_url(
    state: MutableMapping,
    identity: AppIdentity,
) -> str:
    ready, reason = subscription_configuration_status()
    if not ready:
        raise BillingError(reason)

    subscription = load_subscription(state, identity)
    customer_id = str((subscription or {}).get("stripe_customer_id") or "").strip()
    if not customer_id:
        raise BillingError("No Stripe customer is attached to this account yet.")

    result = StripeBillingClient(_stripe_secret()).create_portal_session(
        customer_id=customer_id,
        return_url=f"{_public_url()}/",
    )
    url = str(result.get("url") or "").strip()
    if not url:
        raise BillingError("Stripe Customer Portal did not return a URL.")
    return url
