"""Streamlit panel for production consensus routing with adaptive options promotion."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from market_forecaster.core.options_flow_v2 import load_options_history
from market_forecaster.core.options_promotion import (
    build_adaptive_options_consensus,
    build_options_promotion,
)
from market_forecaster.core.production_consensus import build_production_consensus


def render_production_consensus_panel(
    ensemble_result: dict | None,
    xgb_result,
    ticker: str,
) -> None:
    st.markdown("---")
    st.subheader("Production Consensus")
    st.caption(
        "Validated classic ensemble + gated XGBoost + only historically validated "
        "options horizons whose latest OOS fold is still healthy."
    )

    if not ensemble_result:
        st.info("Run a forecast with Ensemble enabled first.")
        return

    try:
        base_result = build_production_consensus(ensemble_result, xgb_result, ticker)
    except Exception as exc:
        st.warning(f"Production consensus unavailable: {exc}")
        return

    stock_df = st.session_state.get("stock_df")
    current_options = st.session_state.get("options_flow_v2")
    promotion = None

    if current_options and stock_df is not None and not getattr(stock_df, "empty", True):
        try:
            history = load_options_history(ticker, limit=10000)
            promotion = build_options_promotion(history, stock_df, current_options)
        except Exception as exc:
            st.caption(f"Options promotion unavailable: {exc}")

    try:
        result = build_adaptive_options_consensus(base_result, promotion)
    except Exception as exc:
        st.warning(f"Adaptive production consensus unavailable: {exc}")
        return

    st.session_state["production_consensus_result"] = base_result
    st.session_state["options_promotion_result"] = promotion
    st.session_state["adaptive_production_consensus_result"] = result

    xgb_count = len(result.xgb_anchors)
    opt_count = len(result.options_anchors)

    if opt_count:
        st.success(
            "Adaptive production consensus active with historically validated "
            f"options horizon(s): {', '.join(str(a.horizon) for a in result.options_anchors)} sessions."
        )
    elif xgb_count:
        st.success(
            f"Production consensus active with gated XGBoost horizon(s): "
            f"{', '.join(str(a.horizon) for a in result.xgb_anchors)} sessions. "
            "No options horizon is currently promoted."
        )
    else:
        st.warning(
            "No deployable XGBoost or options anchor is active. "
            "The validated classic ensemble remains the production path."
        )

    if promotion is not None:
        if promotion.status == "COLLECTING":
            st.info(
                f"Options promotion is collecting history "
                f"({promotion.unique_sessions} unique sessions). No options weight is applied."
            )
        elif promotion.status == "HOLD":
            st.caption("Options promotion status: HOLD — current evidence is not strong/recent enough.")
        elif promotion.status == "ACTIVE":
            st.caption(
                "Options promotion status: ACTIVE — each promoted options anchor is capped at 15% influence."
            )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=result.dates, y=result.upper,
        mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=result.dates, y=result.lower,
        mode="lines", line=dict(width=0), fill="tonexty",
        fillcolor="rgba(16,185,129,0.10)",
        name="Shifted conformal band", hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=result.dates, y=result.ensemble,
        mode="lines", name="Validated Ensemble",
        line=dict(width=2, dash="dot", color="#64748b"),
    ))

    if opt_count:
        fig.add_trace(go.Scatter(
            x=result.dates, y=result.base_consensus,
            mode="lines", name="Pre-options Consensus",
            line=dict(width=2, dash="dash", color="#059669"),
        ))

    fig.add_trace(go.Scatter(
        x=result.dates, y=result.consensus,
        mode="lines",
        name="Adaptive Production Consensus" if opt_count else "Production Consensus",
        line=dict(width=3, color="#047857"),
    ))

    if result.xgb_anchors:
        anchor_dates = [pd.Timestamp(a.target_date) for a in result.xgb_anchors]
        fig.add_trace(go.Scatter(
            x=anchor_dates,
            y=[a.xgb_base_price for a in result.xgb_anchors],
            mode="markers",
            name="Gated XGB anchors",
            marker=dict(size=10, symbol="diamond", color="#7c3aed"),
            customdata=[
                [a.horizon, a.blend_weight * 100, a.evidence_source]
                for a in result.xgb_anchors
            ],
            hovertemplate=(
                "Horizon %{customdata[0]} sessions<br>"
                "XGB base %{y:.2f}<br>"
                "Blend %{customdata[1]:.1f}%<br>"
                "Evidence %{customdata[2]}<extra></extra>"
            ),
        ))

    if result.options_anchors:
        option_dates = [
            result.dates[min(a.horizon - 1, len(result.dates) - 1)]
            for a in result.options_anchors
        ]
        fig.add_trace(go.Scatter(
            x=option_dates,
            y=[a.target_price for a in result.options_anchors],
            mode="markers",
            name="Validated options anchors",
            marker=dict(size=11, symbol="triangle-up", color="#d97706"),
            customdata=[
                [
                    a.horizon,
                    a.predicted_return * 100,
                    a.blend_weight * 100,
                    a.improvement_pct,
                    a.directional_accuracy_pct,
                ]
                for a in result.options_anchors
            ],
            hovertemplate=(
                "Horizon %{customdata[0]} sessions<br>"
                "Options target %{y:.2f}<br>"
                "Pred return %{customdata[1]:+.2f}%<br>"
                "Blend %{customdata[2]:.1f}%<br>"
                "OOS improvement %{customdata[3]:.1f}%<br>"
                "OOS direction %{customdata[4]:.1f}%<extra></extra>"
            ),
        ))

    fig.update_layout(
        title=f"{ticker} — Adaptive Production Consensus",
        xaxis_title="Date", yaxis_title="Price",
        height=450, hovermode="x unified",
        margin=dict(l=10, r=10, t=50, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

    if result.xgb_anchors:
        st.markdown("**XGBoost deployment anchors**")
        rows = []
        for a in result.xgb_anchors:
            rows.append({
                "Horizon": f"{a.horizon} sessions",
                "Global Gate": a.production_gate,
                "Regime Gate": a.regime_gate,
                "Regime Folds": a.regime_matching_folds,
                "Ensemble Price": round(a.ensemble_price, 2),
                "XGB Base": round(a.xgb_base_price, 2),
                "Blend Weight %": round(a.blend_weight * 100, 1),
                "Improvement %": round(a.improvement_vs_baseline_pct, 1),
                "Direction %": round(a.directional_accuracy_pct, 1),
                "Evidence": a.evidence_source,
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if result.options_anchors:
        st.markdown("**Adaptive options deployment anchors**")
        rows = []
        for a in result.options_anchors:
            rows.append({
                "Horizon": f"{a.horizon} sessions",
                "Global Gate": a.global_gate,
                "Latest Fold": a.recent_fold_gate,
                "Pred Return %": round(a.predicted_return * 100, 2),
                "Target Price": round(a.target_price, 2),
                "Blend Weight %": round(a.blend_weight * 100, 1),
                "Feature Coverage %": round(a.feature_completeness * 100, 1),
                "OOS Improvement %": round(a.improvement_pct, 1),
                "Direction %": round(a.directional_accuracy_pct, 1),
                "Fold Win %": round(a.fold_win_rate * 100, 1),
                "Train Samples": a.training_samples,
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Current regime", result.current_regime)
    with c2:
        end_change = (
            (result.consensus[-1] / result.consensus[0] - 1.0) * 100
            if result.consensus[0] else 0.0
        )
        st.metric("Consensus path change", f"{end_change:+.2f}%")
    with c3:
        st.metric("Active XGB anchors", len(result.xgb_anchors))
    with c4:
        st.metric("Active Options anchors", len(result.options_anchors))

    with st.expander("Consensus safeguards", expanded=False):
        for note in result.notes:
            st.markdown(f"- {note}")
        if promotion is not None:
            for note in promotion.notes:
                st.markdown(f"- Options: {note}")
