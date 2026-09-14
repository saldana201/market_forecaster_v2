"""Streamlit volatility and market-regime dashboard."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from market_forecaster.core.regime import classify_regime, compute_regime_features
from market_forecaster.core.volatility import forecast_volatility


def _pct(value: float, digits: int = 1) -> str:
    return "N/A" if not np.isfinite(value) else f"{value * 100:.{digits}f}%"


def render_regime_panel(stock_df: pd.DataFrame | None, ensemble_result: dict | None = None) -> None:
    st.subheader("Volatility + Regime Engine")
    st.caption(
        "Causal market-state classification. The regime uses only information available through the latest bar; "
        "future observations are never used to assign the current state."
    )

    if stock_df is None or stock_df.empty:
        st.info("Run a forecast first to load price history.")
        return

    try:
        snapshot = classify_regime(stock_df)
        vol = forecast_volatility(stock_df)
        features = compute_regime_features(stock_df)
    except Exception as exc:
        st.warning(f"Regime engine unavailable: {exc}")
        return

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Composite regime", snapshot.composite)
    with c2:
        st.metric("Trend state", snapshot.trend_state)
    with c3:
        st.metric("Volatility state", snapshot.volatility_state)
    with c4:
        st.metric("Vol percentile", f"{snapshot.volatility_percentile * 100:.0f}%")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("20D realized vol", _pct(snapshot.realized_vol_20))
    with c2:
        st.metric("ATR / Price", _pct(snapshot.atr_pct_14))
    with c3:
        st.metric("5D return", _pct(snapshot.return_5d))
    with c4:
        st.metric("252D drawdown", _pct(snapshot.drawdown_252))

    horizon_cols = st.columns(len(vol.forecasts))
    for col, (horizon, value) in zip(horizon_cols, sorted(vol.forecasts.items())):
        with col:
            st.metric(f"Expected vol — {horizon} session{'s' if horizon != 1 else ''}", _pct(value))
    st.caption(f"Volatility method: `{vol.method}` · daily-bar HAR proxy, not intraday realized variance.")

    chart = features.dropna(subset=["realized_vol_20"]).tail(500)
    if not chart.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=chart["Date"], y=chart["realized_vol_20"] * 100,
            mode="lines", name="20D realized volatility",
        ))
        fig.update_layout(
            title="Realized Volatility History",
            yaxis_title="Annualized volatility %",
            xaxis_title="Date",
            height=320,
            hovermode="x unified",
            margin=dict(l=10, r=10, t=45, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

    route_meta = st.session_state.get("regime_routing_meta")
    route_weights = st.session_state.get("regime_routing_weights")
    if route_weights:
        st.success(
            f"Regime routing is armed for the next ensemble run. Source: "
            f"{route_meta.get('source', 'validation folds') if isinstance(route_meta, dict) else 'validation folds'}."
        )
        weight_df = pd.DataFrame({
            "Model": list(route_weights.keys()),
            "Routing Prior %": [round(v * 100, 1) for v in route_weights.values()],
        })
        st.dataframe(weight_df, use_container_width=True, hide_index=True)
    else:
        st.info(
            "No regime routing prior is armed yet. Run the Production Model Zoo in the Backtest tab. "
            "Routing activates only when enough matching validation folds exist and a model passes the global production gate."
        )

    if ensemble_result:
        with st.expander("Current ensemble weighting evidence", expanded=False):
            weights = ensemble_result.get("weights", {})
            if weights:
                df = pd.DataFrame({
                    "Model": list(weights),
                    "Final Ensemble Weight %": [round(weights[k] * 100, 1) for k in weights],
                    "Validation sMAPE": [ensemble_result.get("validation_errors_smape", {}).get(k) for k in weights],
                })
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.caption(f"Weight source: `{ensemble_result.get('weight_source', 'validation_only')}`")
