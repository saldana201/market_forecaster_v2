"""Subscription UI for Market Forecaster 4.1.3."""
from __future__ import annotations

import streamlit as st

from market_forecaster.billing.stripe_client import BillingError
from market_forecaster.core.session_identity import resolve_identity
from market_forecaster.services.subscriptions import (
    create_checkout_url,
    create_portal_url,
    load_subscription,
    normalize_requested_plan,
    requested_plan_is_satisfied,
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



def capture_billing_return() -> None:
    """Consume Stripe return query state once and convert it to session UI state."""
    try:
        raw = st.query_params.get("billing")
    except Exception:
        return

    if isinstance(raw, list):
        raw = raw[0] if raw else None
    result = str(raw or "").strip().lower()
    if result not in {"success", "cancel"}:
        return

    st.session_state["billing_return_notice"] = result
    st.session_state.pop("billing_checkout_url", None)
    st.session_state.pop("billing_checkout_plan", None)

    try:
        del st.query_params["billing"]
    except Exception:
        pass


def render_billing_return_notice() -> None:
    result = st.session_state.pop("billing_return_notice", None)
    if result == "success":
        st.success(
            "Stripe Checkout returned successfully. Subscription status may take a few seconds "
            "to synchronize from the signed webhook."
        )
    elif result == "cancel":
        st.info("Stripe Checkout was canceled. No subscription change was made.")


def render_upgrade_handoff() -> None:
    """Keep a Demo plan choice visible after the user authenticates."""
    identity = resolve_identity(st.session_state)
    if not identity.authenticated:
        return

    requested = normalize_requested_plan(st.session_state.get("requested_plan"))
    if requested is None:
        return

    if requested_plan_is_satisfied(identity, requested):
        st.session_state.pop("requested_plan", None)
        st.session_state.pop("billing_checkout_url", None)
        st.session_state.pop("billing_checkout_plan", None)
        st.success(f"{identity.plan.title()} access is active on this account.")
        return

    ready, reason = subscription_configuration_status()

    with st.container(border=True):
        st.markdown(f"### Continue your {requested.title()} upgrade")
        st.caption(
            "Your plan selection carried over from the Demo. Account verification is complete; "
            "the next step is secure Stripe Checkout."
        )

        if not ready:
            st.info(
                "Your upgrade choice is saved for this session, but billing is not active on this "
                f"deployment yet. {reason}"
            )
            return

        if st.session_state.get("billing_checkout_plan") != requested:
            st.session_state.pop("billing_checkout_url", None)
            st.session_state["billing_checkout_plan"] = requested

        if st.button(
            f"Prepare {requested.title()} Checkout",
            key=f"prepare_requested_{requested}_checkout",
            type="primary",
            use_container_width=True,
        ):
            try:
                st.session_state["billing_checkout_url"] = create_checkout_url(
                    st.session_state,
                    identity,
                    requested,
                )
            except BillingError as exc:
                st.error(str(exc))

        checkout_url = st.session_state.get("billing_checkout_url")
        if checkout_url:
            st.link_button(
                f"Continue to Stripe for {requested.title()}",
                str(checkout_url),
                type="primary",
                use_container_width=True,
            )

        if st.button(
            "Clear upgrade choice",
            key="clear_requested_plan",
            use_container_width=True,
        ):
            st.session_state.pop("requested_plan", None)
            st.session_state.pop("billing_checkout_url", None)
            st.session_state.pop("billing_checkout_plan", None)
            st.rerun()


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
