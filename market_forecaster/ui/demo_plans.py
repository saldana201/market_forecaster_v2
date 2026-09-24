"""Plan comparison and account upgrade entry point for the anonymous Demo."""
from __future__ import annotations

import streamlit as st


def _plan_card(
    *,
    title: str,
    subtitle: str,
    badge: str,
    features: list[str],
    button_label: str,
    key: str,
    featured: bool = False,
    disabled: bool = False,
) -> bool:
    with st.container(border=True):
        if featured:
            st.markdown("**MOST PRACTICAL FOR INDIVIDUAL INVESTORS**")
        st.markdown(f"## {title}")
        st.caption(subtitle)
        st.markdown(f"**{badge}**")
        for feature in features:
            st.markdown(f"✓ {feature}")
        return st.button(
            button_label,
            disabled=disabled,
            use_container_width=True,
            key=key,
            type="primary" if featured else "secondary",
        )


def _go_to_account(plan: str) -> None:
    st.session_state["requested_plan"] = plan
    # Do not mutate the segmented-control key after the widget has been
    # instantiated on this run. Hand the destination to app.py and apply it
    # before the navigation widget is created on the next rerun.
    st.session_state["demo_navigation_pending"] = "◎ Account"
    st.rerun()


def render_demo_plans() -> None:
    st.markdown("## Choose how far you want to take Market Forecaster")
    st.caption(
        "Forecast quality stays consistent across plans. Paid tiers expand the markets you can analyze, "
        "what you can save, and how deeply you can research."
    )

    demo, standard, pro = st.columns(3)
    with demo:
        _plan_card(
            title="Demo",
            subtitle="Explore the forecasting experience",
            badge="$0 · No account required",
            features=[
                "14 curated markets",
                "1D / 5D / 10D / 20D forecasts",
                "Projected price and probability",
                "Session watchlist",
                "Session portfolio",
            ],
            button_label="Current experience",
            key="plan_demo",
            disabled=True,
        )

    with standard:
        standard_clicked = _plan_card(
            title="Standard",
            subtitle="Build your permanent market workspace",
            badge="Subscription plan",
            features=[
                "Custom supported tickers",
                "Persistent watchlists",
                "Persistent portfolios",
                "Forecast history",
                "Basic export",
            ],
            button_label="Create account for Standard",
            key="plan_standard",
            featured=True,
        )
        if standard_clicked:
            _go_to_account("standard")

    with pro:
        pro_clicked = _plan_card(
            title="Pro",
            subtitle="Advanced research and integration",
            badge="Research subscription",
            features=[
                "Everything in Standard",
                "Research Lab",
                "Model Tournament",
                "Feature intelligence",
                "Calibration diagnostics",
                "API access",
            ],
            button_label="Create account for Pro",
            key="plan_pro",
        )
        if pro_clicked:
            _go_to_account("pro")

    st.markdown(
        """
<div class="mf-session-note">
<strong>Secure upgrade flow:</strong>
create and verify your account first. Subscription checkout is then handled on Stripe-hosted pages,
while Market Forecaster reads the resulting subscription state to unlock Standard or Pro entitlements.
</div>
        """,
        unsafe_allow_html=True,
    )
