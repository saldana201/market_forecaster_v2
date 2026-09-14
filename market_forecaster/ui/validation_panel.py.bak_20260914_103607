"""Streamlit Production Validation / Model Zoo panel with regime routing evidence."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from market_forecaster.core.model_zoo import run_model_zoo
from market_forecaster.core.regime import classify_regime, derive_regime_routing, ensemble_weight_names


def _display_name(name: str) -> str:
    return {
        "naive": "Naive",
        "prophet": "Prophet",
        "arima": "ARIMA",
        "ridge": "Ridge",
        "random_forest": "Random Forest",
    }.get(name, name)


def render_validation_panel(req, stock_df: pd.DataFrame | None) -> None:
    st.subheader("Production Validation Lab")
    st.caption(
        "Compare Prophet, ARIMA, Ridge and Random Forest against a mandatory Naive baseline "
        "on identical expanding-window folds. Each fold is also tagged with the regime visible at the end of its training window."
    )

    if stock_df is None or stock_df.empty:
        st.info("Run a forecast first to load market history, then return here to run the Model Zoo.")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        folds = st.slider("Validation folds", 3, 8, 5, key="validation_zoo_folds")
    with c2:
        test_size = st.slider("Rows per test fold", 5, 40, min(20, max(5, req.holdout_days)), key="validation_zoo_test")
    with c3:
        gap = st.slider("Embargo gap (rows)", 0, 10, 1, key="validation_zoo_gap")

    if not st.button("Run Production Model Zoo", type="primary", key="run_production_model_zoo"):
        return

    with st.spinner("Running identical walk-forward folds across models..."):
        try:
            result = run_model_zoo(
                stock_df,
                test_size=test_size,
                n_folds=folds,
                gap=gap,
                prophet_kwargs=req.to_prophet_kwargs(),
            )
            current = classify_regime(stock_df)
            routing = derive_regime_routing(result.folds, result.leaderboard, current)
        except Exception as exc:
            st.error(f"Validation Lab failed: {exc}")
            return

    leaderboard = result.leaderboard.copy()
    leaderboard["model"] = leaderboard["model"].map(_display_name)

    winner = _display_name(result.winner) if result.winner else "None yet"
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Deployable winner", winner)
    with m2:
        st.metric("Naive sMAPE", f"{result.naive_smape:.2f}%")
    with m3:
        st.metric("Folds run", result.config["n_folds_run"])
    with m4:
        st.metric("Current regime", current.composite)

    display = leaderboard.rename(columns={
        "rank": "Rank",
        "model": "Model",
        "smape_mean": "sMAPE Mean %",
        "smape_std": "sMAPE Std %",
        "smape_worst": "Worst Fold %",
        "mase_mean": "MASE",
        "directional_accuracy": "Direction %",
        "fold_win_rate_vs_naive": "Fold Wins vs Naive %",
        "fold_coverage_pct": "Fold Coverage %",
        "improvement_vs_naive_pct": "Improvement vs Naive %",
        "improvement_ci_low_pct": "Improvement CI Low %",
        "improvement_ci_high_pct": "Improvement CI High %",
        "production_gate": "Gate",
    })
    cols = [
        "Rank", "Model", "Gate", "sMAPE Mean %", "sMAPE Std %", "Worst Fold %",
        "MASE", "Direction %", "Fold Coverage %", "Fold Wins vs Naive %", "Improvement vs Naive %",
        "Improvement CI Low %", "Improvement CI High %",
    ]
    st.dataframe(display[[c for c in cols if c in display.columns]], use_container_width=True, hide_index=True)

    if result.winner:
        st.success(
            f"{winner} passed the global production gate: complete fold coverage, at least 2% mean sMAPE "
            "improvement vs Naive, wins at least 60% of paired folds, and retains at least 50% directional accuracy."
        )
    else:
        st.warning(
            "No model passed the production gate. Keep the Naive baseline as the benchmark and do not "
            "promote a more complex model just because it ranked first."
        )

    st.markdown("#### Regime-aware routing")
    if routing.active:
        ensemble_weights = ensemble_weight_names(routing.weights)
        st.session_state["regime_routing_weights"] = ensemble_weights
        st.session_state["regime_routing_meta"] = routing.to_dict()
        route_df = pd.DataFrame({
            "Model": [_display_name(k) for k in routing.weights],
            "Learned Routing Prior %": [round(v * 100, 1) for v in routing.weights.values()],
        })
        st.dataframe(route_df, use_container_width=True, hide_index=True)
        st.success(
            f"Routing prior armed from {routing.matching_folds} matching folds using `{routing.source}`. "
            "Rerun the Forecast to combine this prior with fresh held-out ensemble validation."
        )
    else:
        st.session_state.pop("regime_routing_weights", None)
        st.session_state["regime_routing_meta"] = routing.to_dict()
        st.info(routing.reason)

    with st.expander("Fold-level evidence"):
        fold_df = result.folds.copy()
        fold_df["model"] = fold_df["model"].map(_display_name)
        preferred = [
            "fold", "regime", "trend_state", "volatility_state", "model", "smape",
            "directional_accuracy", "train_end", "test_start", "test_end", "gap",
        ]
        remainder = [c for c in fold_df.columns if c not in preferred]
        st.dataframe(fold_df[[c for c in preferred if c in fold_df.columns] + remainder], use_container_width=True, hide_index=True)

    with st.expander("Validation rules"):
        for note in result.notes:
            st.markdown(f"- {note}")
        st.markdown("- Regime routing only uses globally PASS models and requires at least two matching folds.")
        st.markdown("- Exact composite-regime matches are preferred; volatility-state matching is the only fallback.")
