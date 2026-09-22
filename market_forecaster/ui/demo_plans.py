"""Plan teaser for the anonymous 4.1.0 Demo."""
from __future__ import annotations

import streamlit as st


def render_demo_plans() -> None:
    st.markdown("## Unlock your own market workspace")
    st.caption(
        "The Demo uses the same underlying Forecast Contract quality. Paid plans expand "
        "ticker access, persistence, research tools, and API capabilities."
    )

    demo, standard, pro = st.columns(3)
    with demo:
        with st.container(border=True):
            st.markdown("### Demo")
            st.caption("Explore before creating an account")
            st.markdown(
                """
- 14 curated symbols
- 1D / 5D / 10D / 20D forecasts
- Projected prices and probability
- Session watchlist
- Session portfolio
                """
            )
            st.button("Current plan", disabled=True, use_container_width=True, key="plan_demo")

    with standard:
        with st.container(border=True):
            st.markdown("### Standard")
            st.caption("For your own watchlist and portfolio")
            st.markdown(
                """
- Custom supported tickers
- Persistent watchlists
- Persistent portfolios
- Forecast history
- Basic export
                """
            )
            st.button("Coming in 4.1", disabled=True, use_container_width=True, key="plan_standard")

    with pro:
        with st.container(border=True):
            st.markdown("### Pro")
            st.caption("For advanced market research")
            st.markdown(
                """
- Everything in Standard
- Research Lab
- Model Tournament
- Feature intelligence
- Calibration diagnostics
- API access
                """
            )
            st.button("Coming in 4.1", disabled=True, use_container_width=True, key="plan_pro")

    st.info(
        "We are building account persistence before billing so portfolio and watchlist "
        "data have the correct security model first."
    )
