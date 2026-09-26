"""Legacy/downstream tools kept out of the default Forecast experience."""
from __future__ import annotations

import streamlit as st

from market_forecaster.ui.design_system import (
    render_kpi_strip,
    render_page_header,
    render_section_header,
)
from market_forecaster.ui.portfolio_panel import render_portfolio_panel
from market_forecaster.ui.ranking_panel import render_opportunity_ranking_panel


def render_advanced_tools_panel(current_ticker: str) -> None:
    ticker = str(current_ticker or "").upper().strip() or "—"

    render_page_header(
        "Advanced Tools",
        "Keep legacy ranking and portfolio-overlay research available without mixing it into the canonical Forecast experience.",
        eyebrow="Compatibility workspace",
        badge="Legacy / downstream",
    )
    render_kpi_strip(
        [
            {
                "label": "Current market",
                "value": ticker,
                "caption": "Legacy tools follow the active ticker",
                "tone": "accent",
            },
            {
                "label": "Tool groups",
                "value": "2",
                "caption": "Opportunity ranking + portfolio overlay",
            },
            {
                "label": "Forecast authority",
                "value": "Unaffected",
                "caption": "These tools do not alter canonical model authority",
                "tone": "positive",
            },
        ]
    )

    st.markdown(
        """
<div class="mf-session-note">
<strong>Compatibility workspace:</strong>
these tools remain available for comparison and downstream research, but they are not part of the canonical Forecast Contract authority.
</div>
        """,
        unsafe_allow_html=True,
    )

    ranking_tab, portfolio_tab = st.tabs([
        "Opportunity Ranking",
        "Legacy Portfolio Overlay",
    ])

    with ranking_tab:
        render_section_header(
            "Opportunity ranking",
            "Review the legacy cross-market ranking workflow while keeping it separate from the main forecast product.",
            badge="Legacy research",
        )
        render_opportunity_ranking_panel(current_ticker)

    with portfolio_tab:
        render_section_header(
            "Legacy portfolio overlay",
            "Position-aware research controls retained for compatibility. The account Portfolio workspace remains the primary persistent holdings view.",
            badge="Legacy research",
        )
        render_portfolio_panel()
