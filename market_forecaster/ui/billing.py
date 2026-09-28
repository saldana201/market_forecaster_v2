"""Subscription UI for Market Forecaster 4.1.3."""
from __future__ import annotations

import streamlit as st

from market_forecaster.billing.stripe_client import BillingError
from market_forecaster.core.session_identity import resolve_identity
from market_forecaster.services.subscriptions import (
    ENTITLED_STATUSES,
    create_checkout_url,
    create_portal_url,
    load_subscription,
    normalize_requested_plan,
    requested_plan_is_satisfied,
    stripe_catalog_diagnostics,
    subscription_configuration_diagnostics,
    subscription_configuration_status,
    sync_subscription_identity,
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



PLAN_OPTIONS = ("Standard", "Pro")


def _timestamp_label(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Not yet"
    return raw.replace("T", " ")[:19] + (" UTC" if "Z" in raw or "+" in raw else "")


def _subscription_sync_details(subscription: dict | None) -> dict[str, str]:
    row = subscription or {}
    return {
        "period_end": _timestamp_label(row.get("current_period_end")),
        "event_type": str(row.get("stripe_event_type") or "Not yet"),
        "event_time": _timestamp_label(row.get("stripe_event_created_at")),
        "cancel_at_period_end": "Yes" if row.get("cancel_at_period_end") else "No",
    }


def render_plan_selector(*, title: str = "Choose your subscription tier") -> str:
    """Show and persist an explicit Standard/Pro choice without tying it to auth state."""
    requested = normalize_requested_plan(st.session_state.get("requested_plan"))
    choice_key = "account_plan_choice"
    seed_key = "_account_plan_choice_seed"

    # Authentication may finish after this widget existed on the previous run.
    # Consume any queued selection before instantiating the widget.
    pending_choice = st.session_state.pop("account_plan_choice_pending", None)
    if pending_choice in PLAN_OPTIONS:
        st.session_state[choice_key] = pending_choice
        st.session_state[seed_key] = str(pending_choice).lower()
        requested = normalize_requested_plan(pending_choice)

    # Seed the visible control from the plan selected on the Demo Plans page.
    # This occurs before the widget is instantiated, so it stays within
    # Streamlit's widget-state rules.
    if requested and st.session_state.get(seed_key) != requested:
        st.session_state[choice_key] = requested.title()
        st.session_state[seed_key] = requested
    elif st.session_state.get(choice_key) not in PLAN_OPTIONS:
        initial = (requested or "standard").title()
        st.session_state[choice_key] = initial
        st.session_state[seed_key] = initial.lower()

    previous = normalize_requested_plan(st.session_state.get("requested_plan"))
    st.markdown(f"### {title}")
    choice = st.segmented_control(
        "Subscription tier",
        PLAN_OPTIONS,
        key=choice_key,
        label_visibility="collapsed",
    )
    selected = normalize_requested_plan(choice or st.session_state.get(choice_key)) or "standard"

    if previous != selected:
        st.session_state["requested_plan"] = selected
        st.session_state[seed_key] = selected
        st.session_state.pop("billing_checkout_url", None)
        st.session_state.pop("billing_checkout_plan", None)
    else:
        st.session_state["requested_plan"] = selected

    standard_col, pro_col = st.columns(2)
    with standard_col:
        st.markdown("**Standard**")
        st.caption("Custom tickers · persistent watchlists/portfolios · forecast history · basic export")
    with pro_col:
        st.markdown("**Pro**")
        st.caption("Everything in Standard · Research Lab · advanced diagnostics · API access")

    st.info(
        f"Selected plan: **{selected.title()}**. "
        "This choice stays with you through sign-in or account creation."
    )
    return selected


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
    if result == "success":
        st.session_state["billing_sync_pending"] = True
    else:
        st.session_state.pop("billing_sync_pending", None)
    st.session_state.pop("billing_checkout_url", None)
    st.session_state.pop("billing_checkout_plan", None)

    try:
        del st.query_params["billing"]
    except Exception:
        pass


def render_billing_return_notice() -> None:
    result = st.session_state.pop("billing_return_notice", None)
    if result == "cancel":
        st.session_state.pop("billing_sync_pending", None)
        st.info("Stripe Checkout was canceled. No subscription change was made.")
        return

    pending = bool(st.session_state.get("billing_sync_pending"))
    if result != "success" and not pending:
        return

    identity = resolve_identity(st.session_state)
    if identity.subscription_status in ENTITLED_STATUSES:
        st.session_state.pop("billing_sync_pending", None)
        st.success(
            f"Stripe confirmed the subscription. {identity.plan.title()} access is active."
        )
        return

    st.info(
        "Stripe Checkout returned successfully. Market Forecaster is waiting for the signed "
        "Stripe webhook to confirm the subscription before paid access is unlocked."
    )
    st.caption(
        f"Current billing status: {_status_label(identity.subscription_status)}. "
        "If Stripe has already delivered the webhook, refresh the subscription state below."
    )

    if st.button(
        "Refresh subscription status",
        key="billing_return_refresh_status",
        type="primary",
    ):
        refreshed = sync_subscription_identity(st.session_state, identity)
        if refreshed.subscription_status in ENTITLED_STATUSES:
            st.session_state.pop("billing_sync_pending", None)
        st.rerun()


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


def _render_billing_activation_checklist() -> None:
    with st.expander("Billing activation checklist"):
        checks = subscription_configuration_diagnostics()
        for row in checks:
            icon = "✅" if row.get("ready") else "○"
            st.markdown(
                f"{icon} **{row.get('name')}** — {row.get('detail')}"
            )

        st.caption(
            "Billing mode is an explicit safety boundary: test mode requires an sk_test_ key; "
            "live mode requires an sk_live_ key and an HTTPS public return URL."
        )

        if st.button(
            "Validate Stripe recurring prices (no charge)",
            key="billing_validate_stripe_catalog",
            use_container_width=True,
        ):
            with st.spinner("Checking configured Stripe prices..."):
                st.session_state["billing_catalog_validation"] = (
                    stripe_catalog_diagnostics()
                )

        catalog_rows = st.session_state.get("billing_catalog_validation")
        if isinstance(catalog_rows, list):
            st.markdown("**Stripe catalog validation**")
            for row in catalog_rows:
                icon = "✅" if row.get("ready") else "⚠️"
                plan = str(row.get("plan") or "").title()
                st.markdown(f"{icon} **{plan}** — {row.get('detail')}")
            st.caption(
                "This check reads Stripe Price metadata only. It does not create a Checkout "
                "Session, customer, subscription, invoice, or charge."
            )

        st.caption(
            "The Stripe webhook signing secret is stored in Supabase Edge Function secrets "
            "and is verified separately from the Streamlit application."
        )


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

        selected_plan = render_plan_selector()

        if not ready:
            st.info(
                f"{selected_plan.title()} is selected. Stripe Checkout is not active on this "
                f"deployment yet, so no payment can be started. {reason}"
            )
            _render_billing_activation_checklist()
            return

        subscription = None
        try:
            subscription = load_subscription(st.session_state, identity)
        except Exception:
            subscription = None

        details = _subscription_sync_details(subscription)
        d1, d2, d3 = st.columns(3)
        with d1:
            st.metric("Current period ends", details["period_end"])
        with d2:
            st.metric("Cancel at period end", details["cancel_at_period_end"])
        with d3:
            st.metric("Last billing sync", details["event_time"])

        if details["event_type"] != "Not yet":
            st.caption(f"Last Stripe event: {details['event_type']}")

        if subscription and subscription.get("cancel_at_period_end"):
            st.warning("This subscription is set to cancel at the end of the current billing period.")

        refresh_col, note_col = st.columns([1, 2.2])
        with refresh_col:
            if st.button(
                "Refresh billing status",
                key="billing_panel_refresh_status",
                use_container_width=True,
            ):
                sync_subscription_identity(st.session_state, identity)
                st.rerun()
        with note_col:
            st.caption(
                "Payments are handled on Stripe-hosted pages. Market Forecaster never stores card numbers. "
                "Paid access follows the signed webhook-backed subscription authority."
            )

        already_active = requested_plan_is_satisfied(identity, selected_plan)
        if already_active:
            st.success(f"{selected_plan.title()} access is already active on this account.")
        elif st.button(
            f"Prepare {selected_plan.title()} Checkout",
            key="billing_selected_plan_checkout",
            type="primary",
            use_container_width=True,
        ):
            try:
                st.session_state["billing_checkout_plan"] = selected_plan
                st.session_state["billing_checkout_url"] = create_checkout_url(
                    st.session_state,
                    identity,
                    selected_plan,
                )
            except BillingError as exc:
                st.error(str(exc))

        checkout_url = st.session_state.get("billing_checkout_url")
        checkout_plan = normalize_requested_plan(
            st.session_state.get("billing_checkout_plan")
        )
        if checkout_url and checkout_plan == selected_plan:
            st.link_button(
                f"Continue to Stripe for {selected_plan.title()}",
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
