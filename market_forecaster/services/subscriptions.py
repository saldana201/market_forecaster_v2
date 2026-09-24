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


def subscription_configuration_status() -> tuple[bool, str]:
    if not SUBSCRIPTIONS_ENABLED:
        return False, "SUBSCRIPTIONS_ENABLED is false."
    if not DATABASE_PERSISTENCE_ENABLED:
        return False, "DATABASE_PERSISTENCE_ENABLED must be enabled first."
    if not _stripe_secret():
        return False, "STRIPE_SECRET_KEY is not configured."
    if not _price_id("standard") or not _price_id("pro"):
        return False, "Stripe Standard or Pro price ID is not configured."
    return True, "ready"


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
    result = StripeBillingClient(_stripe_secret()).create_checkout_session(
        user_id=user_id,
        email=email,
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
