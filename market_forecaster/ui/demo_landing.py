"""Anonymous Demo landing experience for Market Forecaster 4.1.0."""
from __future__ import annotations

import streamlit as st

from market_forecaster.core.demo_universe import demo_groups
from market_forecaster.core.session_identity import ensure_demo_session


def render_demo_landing(current_ticker: str | None = None) -> str:
    ensure_demo_session(st.session_state)
    current = str(current_ticker or st.session_state.get("ticker") or "SPY").upper().strip()

    st.markdown("### Explore a Forecast")
    st.caption("Full-quality forecasts for a curated set of symbols. Demo data is session-only.")

    for category, rows in demo_groups().items():
        st.markdown(f"**{category}**")
        cols = st.columns(min(4, len(rows)))
        for idx, row in enumerate(rows):
            with cols[idx % len(cols)]:
                label = f"{row.ticker}\n{row.display_name}"
                if st.button(label, key=f"demo_symbol_{row.ticker}", use_container_width=True):
                    current = row.ticker
                    st.session_state["ticker"] = row.ticker
                    st.session_state["demo_selected_ticker"] = row.ticker
                    st.rerun()

    st.info(
        "Want to analyze another ticker or permanently save your watchlist and portfolio? "
        "Account plans are coming in the next phases of 4.1."
    )
    return current
