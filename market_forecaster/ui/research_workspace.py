"""Guided Research Lab workspace for Market Forecaster 4.0.1."""
from __future__ import annotations

import streamlit as st

from market_forecaster.ui.design_system import (
    render_kpi_strip,
    render_page_header,
    render_section_header,
)
from market_forecaster.ui.feature_ablation_panel import render_feature_ablation_panel
from market_forecaster.ui.forecast_intelligence_panel import render_forecast_intelligence_panel
from market_forecaster.ui.research_panel import render_research_panel
from market_forecaster.ui.uncertainty_panel import render_uncertainty_panel


def render_research_workspace(current_ticker: str) -> None:
    ticker = str(current_ticker or "").upper().strip() or "—"

    render_page_header(
        "Research Lab",
        "Test models, inputs, probability calibration, and Forecast Authority decisions without cluttering the main Forecast workspace.",
        eyebrow="Pro research workspace",
        badge="Advanced diagnostics",
    )
    render_kpi_strip(
        [
            {
                "label": "Current market",
                "value": ticker,
                "caption": "Research context follows the active ticker",
                "tone": "accent",
            },
            {
                "label": "Workflow",
                "value": "4 stages",
                "caption": "Models → inputs → confidence → approval",
            },
            {
                "label": "Forecast horizons",
                "value": "1D–20D",
                "caption": "Research supports the canonical contract horizons",
            },
            {
                "label": "Access",
                "value": "Pro",
                "caption": "Advanced research and authority diagnostics",
                "tone": "positive",
            },
        ]
    )

    st.markdown(
        """
<div class="mf-session-note">
<strong>Recommended research flow:</strong>
compare models first, test whether extra market inputs actually help, validate probability and range behavior,
then review the active forecasting setup.
</div>
        """,
        unsafe_allow_html=True,
    )

    step1, step2, step3, step4 = st.tabs([
        "1 · Compare Models",
        "2 · Test Inputs",
        "3 · Validate Confidence",
        "4 · Approve Setup",
    ])

    with step1:
        render_section_header(
            "Compare forecasting models",
            "Measure which model predicts future returns most consistently under the same historical test conditions.",
            badge="Stage 1",
        )
        render_research_panel(current_ticker)

    with step2:
        render_section_header(
            "Test forecast inputs",
            "Check whether broad-market trend, volatility, rates, credit, the dollar, and other candidate inputs improve out-of-sample performance.",
            badge="Stage 2",
        )
        render_feature_ablation_panel(current_ticker)

    with step3:
        render_section_header(
            "Validate forecast confidence",
            "Measure whether direction probabilities and expected price ranges behave realistically on historical out-of-sample forecasts.",
            badge="Stage 3",
        )
        render_uncertainty_panel(current_ticker)

    with step4:
        render_section_header(
            "Review the active forecasting setup",
            "Inspect the explicit model and approved information used for each horizon before canonical Forecast Contracts are generated.",
            badge="Stage 4",
        )
        render_forecast_intelligence_panel(current_ticker)
