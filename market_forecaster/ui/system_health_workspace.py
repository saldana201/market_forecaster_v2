"""System Health workspace for Market Forecaster 4.0.1."""
from __future__ import annotations

import streamlit as st

from market_forecaster.ui.design_system import (
    render_kpi_strip,
    render_page_header,
    render_section_header,
)
from market_forecaster.ui.deployment_panel import render_deployment_policy_panel
from market_forecaster.ui.governance_panel import render_governance_panel
from market_forecaster.ui.operations_panel import render_operations_panel
from market_forecaster.ui.options_history_panel import render_options_history_panel
from market_forecaster.ui.provider_panel import render_provider_panel
from market_forecaster.ui.validation_panel import render_validation_panel


def render_system_health_workspace(req) -> None:
    stock_df = st.session_state.get("stock_df")
    rows_loaded = 0 if stock_df is None else len(stock_df)

    render_page_header(
        "System Health",
        "Inspect market-data freshness, provider behavior, operational events, and forecast-quality safeguards without cluttering the main Forecast workspace.",
        eyebrow="Operational diagnostics",
        badge="Read-only health view",
    )
    render_kpi_strip(
        [
            {
                "label": "Current market",
                "value": str(req.ticker or "—").upper(),
                "caption": "Diagnostics follow the active ticker",
                "tone": "accent",
            },
            {
                "label": "Market data",
                "value": "Loaded" if rows_loaded else "Not loaded",
                "caption": f"{rows_loaded:,} rows in the active session" if rows_loaded else "Generate or load market data first",
                "tone": "positive" if rows_loaded else "warning",
            },
            {
                "label": "Interval",
                "value": str(req.interval or "—"),
                "caption": "Active market-data granularity",
            },
            {
                "label": "Diagnostic areas",
                "value": "3",
                "caption": "Data · Operations · Forecast Quality",
            },
        ]
    )

    st.markdown(
        """
<div class="mf-session-note">
<strong>System Health is observational.</strong>
These panels surface data/provider state, operational events, governance controls, and validation evidence.
They do not change Forecast Authority or place trades.
</div>
        """,
        unsafe_allow_html=True,
    )

    data_tab, ops_tab, quality_tab = st.tabs([
        "Data Status",
        "Operations",
        "Forecast Quality",
    ])

    with data_tab:
        render_section_header(
            "Market data status",
            "Review provider availability, freshness, failover behavior, and the current options-data snapshot.",
            badge="Data",
        )
        render_provider_panel(req.ticker, stock_df, req.interval)
        with st.expander("Options snapshot history", expanded=False):
            render_options_history_panel(req.ticker, stock_df)

    with ops_tab:
        render_section_header(
            "Operational health",
            "Inspect runtime events, governance controls, and the legacy deployment policy in one place.",
            badge="Operations",
        )
        render_operations_panel(req.ticker, stock_df)
        with st.expander("Governance and audit controls", expanded=False):
            render_governance_panel(req.ticker, stock_df)
        with st.expander("Legacy deployment policy", expanded=False):
            render_deployment_policy_panel(req.ticker)

    with quality_tab:
        render_section_header(
            "Forecast validation",
            "Detailed statistical validation lives here; the Forecast page keeps the evidence summary plain-language.",
            badge="Quality",
        )
        render_validation_panel(req, stock_df)
