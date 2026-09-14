"""
Market Forecaster — Plotly Visualization
Forecast charts, pattern timelines, ensemble comparison.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


def plot_forecast(
    merged_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    title: str,
    tech_df: pd.DataFrame = None,
    show_technicals: bool = True,
):
    """
    Multi-panel forecast chart:
    Row 1: Price + forecast + uncertainty
    Row 2: RSI + MACD (if show_technicals)
    """
    n_rows = 2 if (show_technicals and tech_df is not None) else 1
    heights = [0.7, 0.3] if n_rows == 2 else [1.0]
    subtitles = [title]
    if n_rows == 2:
        subtitles.append("RSI (14) & MACD")

    fig = make_subplots(
        rows=n_rows, cols=1, shared_xaxes=True,
        vertical_spacing=0.06, row_heights=heights,
        subplot_titles=subtitles,
    )

    # --- Row 1: Price ---
    fig.add_trace(go.Scatter(
        x=merged_df["ds"], y=merged_df["y"],
        mode="lines", name="Actual", line=dict(width=2, color="#2563eb"),
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=forecast_df["ds"], y=forecast_df["yhat_upper"],
        mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip",
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=forecast_df["ds"], y=forecast_df["yhat_lower"],
        mode="lines", fill="tonexty", name="Uncertainty",
        line=dict(width=0), fillcolor="rgba(37,99,235,0.12)", hoverinfo="skip",
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=forecast_df["ds"], y=forecast_df["yhat"],
        mode="lines", name="Forecast", line=dict(width=2, dash="dash", color="#dc2626"),
    ), row=1, col=1)

    # Divider line at forecast start
    if not merged_df.empty:
        last_date = merged_df["ds"].max()
        fig.add_vline(x=last_date, line_dash="dot", line_color="rgba(148,163,184,0.6)", row=1, col=1)

    # --- Row 2: Technicals ---
    if n_rows == 2 and tech_df is not None:
        _add_technicals(fig, tech_df, merged_df, row=2)

    fig.update_layout(
        height=500 if n_rows == 1 else 700,
        hovermode="x unified",
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_yaxes(title_text="Price ($)", row=1, col=1)
    if n_rows == 2:
        fig.update_yaxes(title_text="RSI / MACD", row=2, col=1)
    fig.update_xaxes(title_text="Date", row=n_rows, col=1)

    st.plotly_chart(fig, use_container_width=True)


def _add_technicals(fig, tech_df, merged_df, row):
    """Add RSI + MACD to a subplot row."""
    tech = tech_df.copy()
    if isinstance(tech.columns, pd.MultiIndex):
        tech.columns = [str(c[0]) if isinstance(c, tuple) else str(c) for c in tech.columns]

    date_col = "Date" if "Date" in tech.columns else ("ds" if "ds" in tech.columns else None)
    if date_col is None:
        return

    if "RSI_14" in tech.columns:
        tech["__ds"] = pd.to_datetime(tech[date_col])
        rsi = tech[["__ds", "RSI_14"]].dropna().drop_duplicates("__ds").set_index("__ds")["RSI_14"]
        aligned = rsi.reindex(merged_df["ds"])
        fig.add_trace(go.Scatter(x=merged_df["ds"], y=aligned, mode="lines", name="RSI (14)"), row=row, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", annotation_text="Overbought", row=row, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#22c55e", annotation_text="Oversold", row=row, col=1)

    if "MACD_hist" in tech.columns:
        tech["__ds"] = pd.to_datetime(tech[date_col])
        macd = tech[["__ds", "MACD_hist"]].dropna().drop_duplicates("__ds").set_index("__ds")["MACD_hist"]
        aligned = macd.reindex(merged_df["ds"])
        fig.add_trace(go.Bar(x=merged_df["ds"], y=aligned, name="MACD Hist", opacity=0.35), row=row, col=1)


def plot_ensemble(result: dict, ticker: str):
    """Plot ensemble model comparison chart."""
    fig = go.Figure()

    colors = {"arima": "#3b82f6", "rf": "#f97316", "lstm": "#8b5cf6"}
    for name, pred in result["individual"].items():
        fig.add_trace(go.Scatter(
            x=result["dates"], y=pred,
            mode="lines", name=name.upper(),
            line=dict(dash="dot", color=colors.get(name, "gray")), opacity=0.7,
        ))

    fig.add_trace(go.Scatter(
        x=result["dates"], y=result["ensemble"],
        mode="lines", name="Ensemble", line=dict(width=3, color="#16a34a"),
    ))

    fig.add_trace(go.Scatter(
        x=list(result["dates"]) + list(result["dates"][::-1]),
        y=list(result["upper"]) + list(result["lower"][::-1]),
        fill="toself", fillcolor="rgba(22,163,106,0.15)",
        line=dict(color="rgba(0,0,0,0)"), name="95% CI",
    ))

    fig.update_layout(
        title=f"{ticker} — Ensemble Forecast", xaxis_title="Date",
        yaxis_title="Price ($)", height=450, hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


def plot_seasonal_bars(analysis: dict):
    """Plot monthly and day-of-week return charts."""
    if "monthly" in analysis and analysis["monthly"]:
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        values = [analysis["monthly"].get(m, 0) * 100 for m in range(1, 13)]
        fig = go.Figure(go.Bar(
            x=months, y=values,
            marker_color=["#22c55e" if v > 0 else "#ef4444" for v in values],
            text=[f"{v:.2f}%" for v in values], textposition="outside",
        ))
        fig.update_layout(title="Avg Monthly Returns (%)", yaxis_title="Return %", height=300)
        st.plotly_chart(fig, use_container_width=True)

    if "day_of_week" in analysis and analysis["day_of_week"]:
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        values = [analysis["day_of_week"].get(d, 0) * 100 for d in days]
        fig = go.Figure(go.Bar(
            x=days, y=values,
            marker_color=["#22c55e" if v > 0 else "#ef4444" for v in values],
            text=[f"{v:.3f}%" for v in values], textposition="outside",
        ))
        fig.update_layout(title="Avg Returns by Day of Week (%)", yaxis_title="Return %", height=280)
        st.plotly_chart(fig, use_container_width=True)
