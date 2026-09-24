"""Subscription UI for Market Forecaster 4.1.3."""
from __future__ import annotations

import streamlit as st

from market_forecaster.billing.stripe_client import BillingError
from market_forecaster.core.session_identity import resolve_identity
from market_forecaster.services.subscriptions import (
    create_checkout_url,
    create_portal_url,
    load_subscription,
    subscription_configuration_status,
)


def _status_label(status: str) -> str:
    mapping = {
        "none": "No subscription",
        "trialing": "Trial",
        "active": "Active",
        "past_due": "Past due",
        "unpaid": "Unpaid",
        "canceled": "Canceled",
        "incomplete": "Incomplete",
        "incomplete_expired": "Expired",
        "paused": "Paused",
        "unavailable": "Unavailable",
        "bootstrap": "Account access",
    }
    return mapping.get(str(status or "").lower(), str(status or "Unknown").title())


def render_billing_panel() -> None:
    identity = resolve_identity(st.session_state)
    if not identity.authenticated:
        return

    ready, reason = subscription_configuration_status()

    with st.container(border=True):
        st.markdown("### Subscription")
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Current plan", identity.plan.title())
        with c2:
            st.metric("Billing status", _status_label(identity.subscription_status))

        if not ready:
            st.caption(
                "Subscription billing is installed but not active for this deployment yet. "
                f"{reason}"
            )
            return

        subscription = None
        try:
            subscription = load_subscription(st.session_state, identity)
        except Exception:
            subscription = None

        if subscription and subscription.get("cancel_at_period_end"):
            st.warning("This subscription is set to cancel at the end of the current billing period.")

        st.caption(
            "Payments are handled on Stripe-hosted pages. Market Forecaster never stores card numbers."
        )

        standard_col, pro_col = st.columns(2)

        with standard_col:
            if st.button(
                "Choose Standard",
                key="billing_standard_checkout",
                use_container_width=True,
                disabled=identity.plan == "standard"
                and identity.subscription_status in {"active", "trialing", "past_due"},
            ):
                try:
                    st.session_state["billing_checkout_url"] = create_checkout_url(
                        st.session_state,
                        identity,
                        "standard",
                    )
                except BillingError as exc:
                    st.error(str(exc))

        with pro_col:
            if st.button(
                "Choose Pro",
                key="billing_pro_checkout",
                type="primary",
                use_container_width=True,
                disabled=identity.plan == "pro"
                and identity.subscription_status in {"active", "trialing", "past_due"},
            ):
                try:
                    st.session_state["billing_checkout_url"] = create_checkout_url(
                        st.session_state,
                        identity,
                        "pro",
                    )
                except BillingError as exc:
                    st.error(str(exc))

        checkout_url = st.session_state.get("billing_checkout_url")
        if checkout_url:
            st.link_button(
                "Continue to secure Stripe Checkout",
                str(checkout_url),
                type="primary",
                use_container_width=True,
            )

        customer_id = str((subscription or {}).get("stripe_customer_id") or "").strip()
        if customer_id:
            if st.button(
                "Open billing portal",
                key="billing_portal_create",
                use_container_width=True,
            ):
                try:
                    st.session_state["billing_portal_url"] = create_portal_url(
                        st.session_state,
                        identity,
                    )
                except BillingError as exc:
                    st.error(str(exc))

            portal_url = st.session_state.get("billing_portal_url")
            if portal_url:
                st.link_button(
                    "Manage payment method / cancel subscription",
                    str(portal_url),
                    use_container_width=True,
                )
