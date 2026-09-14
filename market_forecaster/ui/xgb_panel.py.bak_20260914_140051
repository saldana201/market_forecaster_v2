"""Streamlit UI for direct multi-horizon XGBoost quantile forecasts."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from market_forecaster.core.xgb_multihorizon import XGBOOST_AVAILABLE, run_xgb_multihorizon


def _pct(v: float) -> str:
    return "N/A" if pd.isna(v) else f"{v:+.2f}%"


def render_xgb_panel(stock_df: pd.DataFrame | None, ticker: str, interval: str = "1d") -> None:
    st.markdown("---")
    st.subheader("XGBoost Multi-Horizon Scenarios")
    st.caption(
        "Direct 1/5/10/20-session cumulative-return models. Bear/Base/Bull are the model's "
        "10th/50th/90th percentile scenarios. Validation is purged and walk-forward."
    )

    if not XGBOOST_AVAILABLE:
        st.warning("XGBoost is not installed. Run `pip install xgboost==3.1.3`, then restart Streamlit.")
        return
    if stock_df is None or stock_df.empty:
        st.info("Run a forecast first to load price history, then run the XGBoost scenario engine.")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        folds = st.slider("XGB validation folds", 2, 6, 4, key="xgb_mh_folds")
    with c2:
        test_size = st.slider("XGB rows/test fold", 12, 40, 24, key="xgb_mh_test_size")
    with c3:
        trees = st.slider("XGB trees/final model", 120, 500, 320, step=40, key="xgb_mh_trees")

    cache_key = f"xgb_multihorizon::{ticker}::{interval}::{folds}::{test_size}::{trees}"
    if st.button("Run Multi-Horizon XGBoost", type="primary", key="run_xgb_multihorizon"):
        with st.spinner("Training quantile XGBoost models and running purged walk-forward validation..."):
            try:
                result = run_xgb_multihorizon(
                    stock_df, ticker,
                    interval=interval,
                    n_folds=folds,
                    test_size=test_size,
                    n_estimators=trees,
                )
                st.session_state[cache_key] = result
                st.session_state["xgb_multihorizon_result"] = result
            except Exception as exc:
                st.error(f"XGBoost multi-horizon run failed: {exc}")
                return

    result = st.session_state.get(cache_key)
    if result is None:
        st.info("Click **Run Multi-Horizon XGBoost** to calculate scenario forecasts.")
        return

    rows = []
    for item in result.forecasts:
        val = item.validation
        rows.append({
            "Horizon": f"{item.horizon} sessions",
            "Gate": val.production_gate,
            "Regime Gate": getattr(val, "regime_gate", "HOLD"),
            "Bear Return": _pct(item.bear_return_pct),
            "Base Return": _pct(item.base_return_pct),
            "Bull Return": _pct(item.bull_return_pct),
            "Bear Price": round(item.bear_price, 2),
            "Base Price": round(item.base_price, 2),
            "Bull Price": round(item.bull_price, 2),
            "Direction %": round(val.directional_accuracy_pct, 1) if pd.notna(val.directional_accuracy_pct) else None,
            "vs Baseline %": round(val.improvement_vs_baseline_pct, 1) if pd.notna(val.improvement_vs_baseline_pct) else None,
            "10-90 Coverage %": round(val.interval_coverage_pct, 1) if pd.notna(val.interval_coverage_pct) else None,
            "Regime Folds": getattr(val, "regime_matching_folds", 0),
            "Regime vs Baseline %": round(getattr(val, "regime_improvement_vs_baseline_pct", float("nan")), 1) if pd.notna(getattr(val, "regime_improvement_vs_baseline_pct", float("nan"))) else None,
        })
    table = pd.DataFrame(rows)
    st.dataframe(table, use_container_width=True, hide_index=True)

    target_dates = [pd.Timestamp(f.target_date) for f in result.forecasts]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=target_dates, y=[f.bull_price for f in result.forecasts],
        mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=target_dates, y=[f.bear_price for f in result.forecasts],
        mode="lines", fill="tonexty", name="Bear-Bull (10-90)",
        line=dict(width=0), fillcolor="rgba(124,58,237,0.14)",
    ))
    fig.add_trace(go.Scatter(
        x=target_dates, y=[f.base_price for f in result.forecasts],
        mode="lines+markers", name="Base (50th percentile)",
        line=dict(width=3, color="#7c3aed"), marker=dict(size=8),
    ))
    fig.add_hline(y=result.current_price, line_dash="dot", annotation_text="Current price")
    fig.update_layout(
        title=f"{result.ticker} — Direct Multi-Horizon XGBoost",
        xaxis_title="Target date", yaxis_title="Price", height=390,
        hovermode="x unified", margin=dict(l=10, r=10, t=50, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

    if result.feature_importance:
        with st.expander("XGBoost feature importance", expanded=False):
            imp = pd.DataFrame(result.feature_importance)
            imp["importance_pct"] = imp["importance"] * 100
            st.bar_chart(imp.set_index("feature")["importance_pct"])
            st.caption("Importance is averaged across the final horizon models and is not causal attribution.")

    passed = [f.horizon for f in result.forecasts if f.validation.production_gate == "PASS"]
    regime_passed = [f.horizon for f in result.forecasts if getattr(f.validation, "regime_gate", "HOLD") == "PASS"]
    if passed:
        st.success(f"Global production gate passed at horizon(s): {', '.join(map(str, passed))} sessions.")
        current_regime = result.config.get("current_regime", "UNKNOWN")
        if regime_passed:
            st.success(
                f"Current regime `{current_regime}` also passed at horizon(s): "
                f"{', '.join(map(str, regime_passed))} sessions. These anchors may receive higher consensus weight."
            )
        else:
            st.info(
                f"Current regime: `{current_regime}`. No horizon has enough matching regime evidence yet; "
                "globally PASS horizons remain capped at conservative consensus weights."
            )
    else:
        st.warning("No XGBoost horizon passed the production gate yet. Keep it as research evidence rather than routing model weight to it.")

    with st.expander("Methodology / safeguards", expanded=False):
        for note in result.notes:
            st.markdown(f"- {note}")
