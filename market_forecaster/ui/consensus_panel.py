"""Streamlit panel for production consensus routing."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from market_forecaster.core.production_consensus import build_production_consensus


def render_production_consensus_panel(
    ensemble_result: dict | None,
    xgb_result,
    ticker: str,
) -> None:
    st.markdown("---")
    st.subheader("Production Consensus")
    st.caption(
        "Validated classic ensemble + only XGBoost horizons that pass deployment gates. "
        "Regime-confirmed XGBoost evidence can earn more weight; global-only PASS stays conservative."
    )

    if not ensemble_result:
        st.info("Run a forecast with Ensemble enabled first.")
        return
    if xgb_result is None:
        st.info("Run Multi-Horizon XGBoost above. Production consensus activates only after validation evidence exists.")
        return

    try:
        result = build_production_consensus(ensemble_result, xgb_result, ticker)
    except Exception as exc:
        st.warning(f"Production consensus unavailable: {exc}")
        return

    st.session_state["production_consensus_result"] = result

    if result.status == "ENSEMBLE_ONLY":
        st.warning("No deployable XGBoost anchor is active. The validated classic ensemble remains the production path.")
    else:
        st.success(
            f"Production consensus active with gated XGBoost horizon(s): "
            f"{', '.join(map(str, result.used_horizons))} sessions."
        )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=result.dates,
        y=result.upper,
        mode="lines",
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=result.dates,
        y=result.lower,
        mode="lines",
        line=dict(width=0),
        fill="tonexty",
        fillcolor="rgba(16,185,129,0.10)",
        name="Shifted conformal band",
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=result.dates,
        y=result.ensemble,
        mode="lines",
        name="Validated Ensemble",
        line=dict(width=2, dash="dot", color="#64748b"),
    ))
    fig.add_trace(go.Scatter(
        x=result.dates,
        y=result.consensus,
        mode="lines",
        name="Production Consensus",
        line=dict(width=3, color="#059669"),
    ))

    if result.anchors:
        anchor_dates = [pd.Timestamp(a.target_date) for a in result.anchors]
        fig.add_trace(go.Scatter(
            x=anchor_dates,
            y=[a.xgb_base_price for a in result.anchors],
            mode="markers",
            name="Gated XGB anchors",
            marker=dict(size=10, symbol="diamond", color="#7c3aed"),
            customdata=[[a.horizon, a.blend_weight * 100, a.evidence_source] for a in result.anchors],
            hovertemplate=(
                "Horizon %{customdata[0]} sessions<br>"
                "XGB base %{y:.2f}<br>"
                "Blend %{customdata[1]:.1f}%<br>"
                "Evidence %{customdata[2]}<extra></extra>"
            ),
        ))

    fig.update_layout(
        title=f"{ticker} — Production Consensus Forecast",
        xaxis_title="Date",
        yaxis_title="Price",
        height=430,
        hovermode="x unified",
        margin=dict(l=10, r=10, t=50, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

    if result.anchors:
        rows = []
        for a in result.anchors:
            rows.append({
                "Horizon": f"{a.horizon} sessions",
                "Global Gate": a.production_gate,
                "Regime Gate": a.regime_gate,
                "Regime Folds": a.regime_matching_folds,
                "Ensemble Price": round(a.ensemble_price, 2),
                "XGB Base": round(a.xgb_base_price, 2),
                "XGB Bear": round(a.xgb_bear_price, 2),
                "XGB Bull": round(a.xgb_bull_price, 2),
                "Blend Weight %": round(a.blend_weight * 100, 1),
                "Improvement vs Baseline %": round(a.improvement_vs_baseline_pct, 1),
                "Direction %": round(a.directional_accuracy_pct, 1),
                "Evidence": a.evidence_source,
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Current regime", result.current_regime)
    with c2:
        end_change = (result.consensus[-1] / result.consensus[0] - 1.0) * 100 if result.consensus[0] else 0.0
        st.metric("Consensus path change", f"{end_change:+.2f}%")
    with c3:
        st.metric("Active XGB anchors", len(result.anchors))

    with st.expander("Consensus safeguards", expanded=False):
        for note in result.notes:
            st.markdown(f"- {note}")
