"""Guided Research Lab workspace for Market Forecaster 4.0.1."""
from __future__ import annotations

import streamlit as st

from market_forecaster.ui.research_panel import render_research_panel
from market_forecaster.ui.feature_ablation_panel import render_feature_ablation_panel
from market_forecaster.ui.uncertainty_panel import render_uncertainty_panel
from market_forecaster.ui.forecast_intelligence_panel import render_forecast_intelligence_panel


def render_research_workspace(current_ticker: str) -> None:
    st.header("Research Lab")
    st.write(
        "Use this workspace when you want to test or approve the forecasting setup. "
        "The main Forecast page is intentionally simpler."
    )
    st.info(
        "Recommended order: compare models → test market inputs → validate confidence → approve the active forecasting setup."
    )

    step1, step2, step3, step4 = st.tabs([
        "1 · Compare Models",
        "2 · Test Inputs",
        "3 · Validate Confidence",
        "4 · Approve Setup",
    ])

    with step1:
        st.subheader("Compare forecasting models")
        st.caption(
            "Find out which model predicts future returns most consistently under the same historical test conditions."
        )
        render_research_panel(current_ticker)

    with step2:
        st.subheader("Test forecast inputs")
        st.caption(
            "Check whether extra market information such as broad-market trend, volatility, rates, credit, or the dollar actually improves forecasts."
        )
        render_feature_ablation_panel(current_ticker)

    with step3:
        st.subheader("Validate forecast confidence")
        st.caption(
            "Measure whether direction probabilities and expected price ranges behave realistically on historical out-of-sample forecasts."
        )
        render_uncertainty_panel(current_ticker)

    with step4:
        st.subheader("Approve the active forecasting setup")
        st.caption(
            "Choose the explicit model and approved market information used for each forecast horizon, then generate canonical forecast contracts."
        )
        render_forecast_intelligence_panel(current_ticker)
