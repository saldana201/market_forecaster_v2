"""Plan comparison teaser for the anonymous Market Forecaster Demo."""
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
) -> None:
    with st.container(border=True):
        if featured:
            st.markdown("**MOST PRACTICAL FOR INDIVIDUAL INVESTORS**")
        st.markdown(f"## {title}")
        st.caption(subtitle)
        st.markdown(f"**{badge}**")
        for feature in features:
            st.markdown(f"✓ {feature}")
        st.button(
            button_label,
            disabled=True,
            use_container_width=True,
            key=key,
            type="primary" if featured else "secondary",
        )


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
        )

    with standard:
        _plan_card(
            title="Standard",
            subtitle="Build your permanent market workspace",
            badge="Account plan · Coming next",
            features=[
                "Custom supported tickers",
                "Persistent watchlists",
                "Persistent portfolios",
                "Forecast history",
                "Basic export",
            ],
            button_label="Account access coming soon",
            key="plan_standard",
            featured=True,
        )

    with pro:
        _plan_card(
            title="Pro",
            subtitle="Advanced research and integration",
            badge="Research plan · Later in 4.1",
            features=[
                "Everything in Standard",
                "Research Lab",
                "Model Tournament",
                "Feature intelligence",
                "Calibration diagnostics",
                "API access",
            ],
            button_label="Pro access coming soon",
            key="plan_pro",
        )

    st.markdown(
        """
<div class="mf-session-note">
<strong>Why accounts come before billing:</strong>
we are establishing secure identity and user-isolated persistence first, so watchlists and portfolio data
have the correct ownership model before subscriptions are activated.
</div>
        """,
        unsafe_allow_html=True,
    )
