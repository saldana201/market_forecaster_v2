"""Legacy/downstream tools kept out of the default Forecast experience."""
from __future__ import annotations

import streamlit as st

from market_forecaster.ui.ranking_panel import render_opportunity_ranking_panel
from market_forecaster.ui.portfolio_panel import render_portfolio_panel


def render_advanced_tools_panel(current_ticker: str) -> None:
    with st.expander("Legacy downstream tools", expanded=False):
        st.caption(
            "These tools remain available for compatibility, but they are not part of the canonical 4.0 forecasting authority."
        )
        render_opportunity_ranking_panel(current_ticker)
        st.markdown("---")
        render_portfolio_panel()
