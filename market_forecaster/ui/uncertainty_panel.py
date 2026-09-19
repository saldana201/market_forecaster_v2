"""Probability Calibration & Adaptive Uncertainty UI for Market Forecaster 3.9."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.feature_store import build_feature_store
from market_forecaster.core.market_context import (
    ALL_CONTEXT_FAMILIES,
    FAMILY_DESCRIPTIONS,
    build_market_context,
)
from market_forecaster.core.model_tournament import model_registry
from market_forecaster.core.uncertainty_calibration import run_uncertainty_research


def _available_models() -> list[str]:
    return [
        row["name"]
        for row in model_registry()
        if row["available"] and row["name"] not in {"zero_return", "historical_mean"}
    ]


def render_uncertainty_panel(current_ticker: str) -> None:
    st.subheader("🎯 Probability Calibration & Adaptive Uncertainty — 3.9")
    st.caption(
        "Convert point forecasts into calibrated P(up) and empirically checked "
        "80%/90% price ranges using only earlier out-of-sample forecast errors."
    )

    available = _available_models()
    default_index = available.index("xgboost") if "xgboost" in available else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        period = st.selectbox(
            "Calibration history",
            ["5y", "10y"],
            index=1,
            key="uncertainty_period",
        )
    with c2:
        model = st.selectbox(
            "Forecast model",
            available,
            index=default_index,
            key="uncertainty_model",
        )
    with c3:
        folds = st.slider(
            "OOS folds",
            4, 8, 6, 1,
            key="uncertainty_folds",
        )
    with c4:
        test_size = st.slider(
            "OOS observations/fold",
            15, 40, 20, 5,
            key="uncertainty_test_size",
        )

    w1, w2 = st.columns(2)
    with w1:
        window_label = st.selectbox(
            "Adaptive calibration window",
            ["60", "120", "250", "All OOS history"],
            index=1,
            key="uncertainty_window",
            help="Recent OOS forecast errors are used to adapt interval width and probability mapping.",
        )
    with w2:
        context_family = st.selectbox(
            "Optional 3.8 context family",
            ["none", *ALL_CONTEXT_FAMILIES],
            index=0,
            format_func=lambda x: (
                "Base 3.6 features only"
                if x == "none"
                else f"{x} — {FAMILY_DESCRIPTIONS[x]}"
            ),
            key="uncertainty_context_family",
        )

    sector_ticker = ""
    if context_family == "sector":
        sector_ticker = st.text_input(
            "Sector ETF for this uncertainty run",
            value="",
            placeholder="Example: XLK",
            key="uncertainty_sector_ticker",
        ).upper().strip()

    registry = {row["name"]: row for row in model_registry()}
    if registry.get(model, {}).get("sequence"):
        st.warning(
            "Sequence-model calibration is slower because the selected deep model "
            "is retrained inside every OOS fold."
        )
        d1, d2 = st.columns(2)
        with d1:
            sequence_lookback = st.slider(
                "Sequence lookback",
                10, 60, 20, 5,
                key="uncertainty_sequence_lookback",
            )
        with d2:
            deep_epochs = st.slider(
                "Deep training epochs",
                3, 40, 15, 1,
                key="uncertainty_deep_epochs",
            )
    else:
        sequence_lookback = 20
        deep_epochs = 15

    calibration_window = None if window_label == "All OOS history" else int(window_label)

    if st.button(
        "Run Calibrated Forecast",
        type="primary",
        key="run_uncertainty_research",
    ):
        if context_family == "sector" and not sector_ticker:
            st.error("Enter a sector ETF or select a different context family.")
        else:
            with st.spinner(
                "Generating OOS forecasts, calibrating probabilities, and measuring interval coverage..."
            ):
                try:
                    market = fetch_stock_data(current_ticker, period, "1d")
                    if market.empty:
                        st.error(f"No market data available for {current_ticker}.")
                    else:
                        feature_frame, metadata = build_feature_store(market, current_ticker)

                        context_info = None
                        if context_family != "none":
                            feature_frame, context_registry = build_market_context(
                                feature_frame,
                                current_ticker,
                                period=period,
                                families=[context_family],
                                sector_ticker=sector_ticker or None,
                            )
                            context_info = context_registry.get(context_family, {})
                            if not context_info.get("available"):
                                st.warning(
                                    f"{context_family} context does not have sufficient "
                                    "coverage. Running the base feature set instead."
                                )
                                feature_frame, metadata = build_feature_store(market, current_ticker)
                                context_family_used = "none"
                            else:
                                context_family_used = context_family
                        else:
                            context_family_used = "none"

                        result = run_uncertainty_research(
                            feature_frame,
                            ticker=current_ticker,
                            model=model,
                            n_splits=folds,
                            test_size=test_size,
                            calibration_window=calibration_window,
                            sequence_lookback=sequence_lookback,
                            deep_epochs=deep_epochs,
                        )
                        result["dataset_metadata"] = metadata.to_dict()
                        result["context_family"] = context_family_used
                        result["context_info"] = context_info
                        st.session_state["uncertainty_research_result"] = result
                except Exception as exc:
                    st.error(f"Uncertainty research failed: {exc}")

    result = st.session_state.get("uncertainty_research_result")
    if not result or result.get("ticker") != current_ticker.upper():
        st.info(
            "Run the calibrated forecast to estimate P(up) and adaptive price ranges "
            "for 1D / 5D / 10D / 20D."
        )
        return

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Model", result.get("model", "N/A"))
    with c2:
        st.metric("Features", result.get("feature_count", 0))
    with c3:
        st.metric("Context", result.get("context_family", "none"))
    with c4:
        window = result.get("calibration_window")
        st.metric("Calibration Window", "All" if window is None else str(window))

    current = pd.DataFrame(result.get("current_forecasts", []))
    if not current.empty:
        display = current.rename(columns={
            "horizon": "Horizon",
            "target_date": "Target Date",
            "current_price": "Current Price",
            "predicted_return_pct": "Expected Return %",
            "predicted_price": "Projected Price",
            "prob_up_pct": "P(up) %",
            "calibration_status": "Calibration",
            "calibration_samples": "OOS Samples",
            "lower_price_80": "80% Low",
            "upper_price_80": "80% High",
            "lower_price_90": "90% Low",
            "upper_price_90": "90% High",
        })
        preferred = [
            "Horizon", "Target Date", "Current Price", "Expected Return %",
            "Projected Price", "P(up) %", "Calibration", "OOS Samples",
            "80% Low", "80% High", "90% Low", "90% High",
        ]
        st.markdown("**Current calibrated forecasts**")
        st.dataframe(
            display[[c for c in preferred if c in display.columns]],
            use_container_width=True,
            hide_index=True,
        )

        provisional = current[current["calibration_status"] != "CALIBRATED"]
        if not provisional.empty:
            st.warning(
                "Some horizons have limited OOS calibration history. Treat their "
                "probabilities/ranges as provisional until more OOS evidence accumulates."
            )

    diagnostics = pd.DataFrame(result.get("calibration_summaries", []))
    if not diagnostics.empty:
        display = diagnostics.rename(columns={
            "horizon": "Horizon",
            "oos_records": "OOS Records",
            "probability_eval_records": "P(up) Eval",
            "brier_score": "Brier",
            "brier_skill_vs_50_pct": "Brier Skill vs 50% %",
            "expected_calibration_error": "ECE",
            "coverage_80_pct": "80% Coverage",
            "avg_width_bps_80": "80% Width (bps)",
            "interval_eval_records_80": "80% Eval",
            "coverage_90_pct": "90% Coverage",
            "avg_width_bps_90": "90% Width (bps)",
            "interval_eval_records_90": "90% Eval",
        })
        preferred = [
            "Horizon", "OOS Records", "P(up) Eval", "Brier",
            "Brier Skill vs 50% %", "ECE",
            "80% Coverage", "80% Width (bps)", "80% Eval",
            "90% Coverage", "90% Width (bps)", "90% Eval",
        ]
        st.markdown("**Prequential calibration diagnostics**")
        st.dataframe(
            display[[c for c in preferred if c in display.columns]],
            use_container_width=True,
            hide_index=True,
        )

    if result.get("model_errors"):
        with st.expander(f"Model/fold errors ({len(result['model_errors'])})"):
            st.dataframe(
                pd.DataFrame(result["model_errors"]),
                use_container_width=True,
                hide_index=True,
            )

    with st.expander("3.9 methodology"):
        for note in result.get("notes", []):
            st.markdown(f"- {note}")
        st.markdown(
            "- Brier score evaluates probabilistic direction forecasts; lower is better."
        )
        st.markdown(
            "- ECE is the expected calibration error; lower means predicted probabilities "
            "better match observed frequencies."
        )
        st.markdown(
            "- Interval coverage should be compared with its nominal target (80% or 90%). "
            "Too-low coverage means the range is too narrow; persistent over-coverage can mean it is unnecessarily wide."
        )
        st.markdown(
            "- The rolling calibration window adapts to recent OOS error behavior but does "
            "not make a guarantee that future financial returns are exchangeable."
        )
