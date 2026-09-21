"""System Health workspace for Market Forecaster 4.0.1."""
from __future__ import annotations

import streamlit as st

from market_forecaster.ui.provider_panel import render_provider_panel
from market_forecaster.ui.operations_panel import render_operations_panel
from market_forecaster.ui.governance_panel import render_governance_panel
from market_forecaster.ui.deployment_panel import render_deployment_policy_panel
from market_forecaster.ui.options_history_panel import render_options_history_panel
from market_forecaster.ui.validation_panel import render_validation_panel


def render_system_health_workspace(req) -> None:
    st.header("System Health")
    st.write(
        "Check data freshness, provider status, operational events, and forecast-quality safeguards. "
        "These diagnostics are separated from the main forecast so they do not distract from the prediction itself."
    )

    data_tab, ops_tab, quality_tab = st.tabs([
        "Data Status",
        "Operations",
        "Forecast Quality",
    ])

    stock_df = st.session_state.get("stock_df")

    with data_tab:
        st.subheader("Market data status")
        render_provider_panel(req.ticker, stock_df, req.interval)
        with st.expander("Options snapshot history", expanded=False):
            render_options_history_panel(req.ticker, stock_df)

    with ops_tab:
        st.subheader("Operational health")
        render_operations_panel(req.ticker, stock_df)
        with st.expander("Governance and audit controls", expanded=False):
            render_governance_panel(req.ticker, stock_df)
        with st.expander("Legacy deployment policy", expanded=False):
            render_deployment_policy_panel(req.ticker)

    with quality_tab:
        st.subheader("Forecast validation")
        st.caption(
            "Detailed statistical validation lives here. Plain-language forecast evidence is shown on the Forecast page."
        )
        render_validation_panel(req, stock_df)
