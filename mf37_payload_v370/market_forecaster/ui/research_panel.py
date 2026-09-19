"""Forecast Research / Model Tournament UI for Market Forecaster 3.7."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.feature_store import build_feature_store
from market_forecaster.core.experiment_runner import (
    DEFAULT_MODELS,
    TOURNAMENT_MODELS,
    run_research_experiment,
)
from market_forecaster.core.model_tournament import model_registry


def _default_models(mode: str) -> list[str]:
    registry = {row["name"]: row for row in model_registry()}
    if mode == "Fast core":
        return [name for name in DEFAULT_MODELS if registry.get(name, {}).get("available")]
    if mode == "Full tabular":
        return [
            name for name in TOURNAMENT_MODELS
            if registry.get(name, {}).get("available") and not registry.get(name, {}).get("sequence")
        ]
    return [name for name in TOURNAMENT_MODELS if registry.get(name, {}).get("available")]


def render_research_panel(current_ticker: str) -> None:
    st.subheader("🧪 Model Tournament — 3.7")
    st.caption(
        "Forecast research only. Every challenger uses the same 3.6 causal feature store, "
        "1D/5D/10D/20D targets, chronological folds and horizon-aware embargo. "
        "Tournament results cannot change production routing or deployment."
    )

    registry_rows = model_registry()
    registry = {row["name"]: row for row in registry_rows}

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        period = st.selectbox(
            "Research history",
            ["2y", "5y", "10y"],
            index=1,
            key="research_period",
        )
    with c2:
        folds = st.slider(
            "Walk-forward folds",
            3, 8, 5, 1,
            key="research_folds",
        )
    with c3:
        test_size = st.slider(
            "Observations / test fold",
            10, 40, 20, 5,
            key="research_test_size",
        )
    with c4:
        mode = st.selectbox(
            "Tournament preset",
            ["Fast core", "Full tabular", "Deep research"],
            index=0,
            key="research_tournament_mode",
        )

    available_names = [row["name"] for row in registry_rows if row["available"]]
    unavailable_names = [row["name"] for row in registry_rows if not row["available"]]
    defaults = _default_models(mode)

    selected_models = st.multiselect(
        "Research models",
        available_names,
        default=defaults,
        key=f"research_models_{mode}",
        help="XGBoost is the nonlinear reference. Optional LightGBM/CatBoost/PyTorch models appear only when installed.",
    )

    selected_deep = [name for name in selected_models if registry.get(name, {}).get("sequence")]
    sequence_lookback = 20
    deep_epochs = 15
    if selected_deep:
        st.warning(
            "Deep research is materially slower because each sequence model is retrained inside every walk-forward fold."
        )
        d1, d2 = st.columns(2)
        with d1:
            sequence_lookback = st.slider(
                "Sequence lookback",
                10, 60, 20, 5,
                key="research_sequence_lookback",
            )
        with d2:
            deep_epochs = st.slider(
                "Deep training epochs",
                3, 40, 15, 1,
                key="research_deep_epochs",
            )

    with st.expander("Model availability"):
        status_df = pd.DataFrame(registry_rows)
        status_df["status"] = status_df["available"].map({True: "Available", False: "Not installed"})
        st.dataframe(
            status_df[["name", "family", "dependency", "status", "description"]],
            use_container_width=True,
            hide_index=True,
        )
        if unavailable_names:
            st.caption(
                "Unavailable optional challengers: " + ", ".join(unavailable_names)
                + ". The production runtime does not require them."
            )

    if st.button(
        "Run 1D / 5D / 10D / 20D Tournament",
        type="primary",
        key="run_model_tournament",
    ):
        if not selected_models:
            st.error("Select at least one research model.")
        else:
            with st.spinner("Running leakage-controlled model tournament..."):
                try:
                    market = fetch_stock_data(current_ticker, period, "1d")
                    if market.empty:
                        st.error(f"No research market data available for {current_ticker}.")
                    else:
                        feature_frame, metadata = build_feature_store(market, current_ticker)
                        result = run_research_experiment(
                            feature_frame,
                            models=selected_models,
                            n_splits=folds,
                            test_size=test_size,
                            sequence_lookback=sequence_lookback,
                            deep_epochs=deep_epochs,
                        )
                        result["ticker"] = current_ticker.upper()
                        result["dataset_metadata"] = metadata.to_dict()
                        st.session_state["research_foundation_result"] = result
                except Exception as exc:
                    st.error(f"Model tournament failed: {exc}")

    result = st.session_state.get("research_foundation_result")
    if not result or result.get("ticker") != current_ticker.upper():
        st.info(
            "Run the tournament to compare models under one common leakage-safe protocol."
        )
        return

    meta = result.get("dataset_metadata", {})
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Protocol", result.get("protocol_version", "N/A"))
    with c2:
        st.metric("Features", result.get("feature_count", 0))
    with c3:
        st.metric("Rows", meta.get("row_count", 0))
    with c4:
        st.metric("Provider", meta.get("provider") or "Unknown")

    if result.get("models_unavailable"):
        st.warning(
            "Skipped unavailable models: " + ", ".join(result["models_unavailable"])
        )
    if result.get("model_errors"):
        with st.expander(f"Model/fold errors ({len(result['model_errors'])})"):
            st.dataframe(pd.DataFrame(result["model_errors"]), use_container_width=True, hide_index=True)

    leaders = pd.DataFrame(result.get("leaders_by_horizon", []))
    if not leaders.empty:
        st.markdown("**Lowest OOS return-MAE by horizon (descriptive tournament ordering)**")
        leaders_display = leaders.rename(columns={
            "horizon": "Horizon",
            "model": "Model",
            "return_mae_bps": "Return MAE (bps)",
            "directional_accuracy_pct": "Direction %",
            "research_status": "Vs Zero",
            "challenger_status": "Vs XGBoost",
        })
        st.dataframe(leaders_display, use_container_width=True, hide_index=True)

    summaries = pd.DataFrame(result.get("summaries", []))
    if summaries.empty:
        st.warning("No valid folds were produced. Increase history or reduce fold/test size.")
        return

    display = summaries.rename(columns={
        "horizon": "Horizon",
        "tournament_rank": "Rank",
        "model": "Model",
        "model_family": "Family",
        "research_status": "Vs Zero",
        "challenger_status": "Vs XGBoost",
        "folds_run": "Folds",
        "observations": "OOS Obs",
        "return_mae_bps": "Return MAE (bps)",
        "return_rmse_bps": "Return RMSE (bps)",
        "directional_accuracy_pct": "Direction %",
        "price_smape_pct": "Price sMAPE %",
        "improvement_vs_zero_mae_pct": "Lift vs Zero %",
        "improvement_ci_low_pct": "Zero CI Low %",
        "improvement_ci_high_pct": "Zero CI High %",
        "improvement_vs_xgb_mae_pct": "Lift vs XGB %",
        "fold_win_rate_vs_xgb_pct": "Win vs XGB %",
        "xgb_lift_ci_low_pct": "XGB CI Low %",
        "xgb_lift_ci_high_pct": "XGB CI High %",
    })
    preferred = [
        "Horizon", "Rank", "Model", "Family", "Vs Zero", "Vs XGBoost",
        "Folds", "OOS Obs", "Return MAE (bps)", "Return RMSE (bps)",
        "Direction %", "Price sMAPE %", "Lift vs Zero %", "Zero CI Low %",
        "Zero CI High %", "Lift vs XGB %", "Win vs XGB %", "XGB CI Low %",
        "XGB CI High %",
    ]
    st.dataframe(
        display[[c for c in preferred if c in display.columns]].sort_values(["Horizon", "Rank"]),
        use_container_width=True,
        hide_index=True,
    )

    challengers = summaries[summaries["challenger_status"] == "CHALLENGER_PROMISING"]
    if not challengers.empty:
        st.success(
            "Challengers with positive paired-fold evidence against XGBoost: "
            + ", ".join(
                f"{row.model} ({int(row.horizon)}D)" for row in challengers.itertuples()
            )
            + ". Next step is broader cross-ticker confirmation, not production promotion."
        )
    else:
        st.info(
            "No challenger currently clears the stricter evidence threshold against XGBoost. "
            "Keeping the benchmark is a valid research result."
        )

    with st.expander("3.7 tournament methodology"):
        for note in result.get("notes", []):
            st.markdown(f"- {note}")
        st.markdown("- Canonical target remains `log(Close[t+h] / Close[t])` for 1D/5D/10D/20D.")
        st.markdown("- `CHALLENGER_PROMISING` requires positive evidence versus XGBoost, not merely versus zero-return.")
        st.markdown("- Deep models use only feature history ending at each forecast origin; target labels remain purged by the same horizon rule.")
