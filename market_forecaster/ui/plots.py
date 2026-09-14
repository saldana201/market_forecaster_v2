"""
Market Forecaster — Plotly Visualization
Forecast charts, historical fit, future projection, technicals, and ensemble comparison.

Production note:
The historical Prophet fit is a visualization only. Model performance metrics must come
from the separate out-of-sample validation path, never from the fitted historical line.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


def _clean_history(history_df: pd.DataFrame | None, fallback_df: pd.DataFrame) -> pd.DataFrame:
    """Return a clean full-history frame with ds/y columns for plotting actual prices."""
    candidate = history_df if history_df is not None and not history_df.empty else fallback_df
    if candidate is None or candidate.empty:
        return pd.DataFrame(columns=["ds", "y"])

    hist = candidate.copy()
    if "ds" not in hist.columns:
        for col in ("Date", "Datetime"):
            if col in hist.columns:
                hist = hist.rename(columns={col: "ds"})
                break
    if "y" not in hist.columns:
        for col in ("Close", "Adj Close"):
            if col in hist.columns:
                obj = hist[col]
                if isinstance(obj, pd.DataFrame):
                    obj = obj.iloc[:, 0]
                hist["y"] = pd.to_numeric(obj, errors="coerce")
                break

    if "ds" not in hist.columns or "y" not in hist.columns:
        return pd.DataFrame(columns=["ds", "y"])

    hist["ds"] = pd.to_datetime(hist["ds"], errors="coerce").dt.tz_localize(None)
    hist["y"] = pd.to_numeric(hist["y"], errors="coerce")
    return (
        hist[["ds", "y"]]
        .dropna()
        .drop_duplicates("ds", keep="last")
        .sort_values("ds")
        .reset_index(drop=True)
    )


def plot_forecast(
    merged_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    title: str,
    tech_df: pd.DataFrame = None,
    show_technicals: bool = True,
    history_df: pd.DataFrame | None = None,
    pattern_scores: dict | None = None,
):
    """
    Multi-panel forecast chart.

    Row 1 shows:
      * full historical Actual price
      * historical fitted model path across the full timeline
      * the same forecast line continuing into the future
      * forecast uncertainty and a clear future-region divider

    Row 2 shows RSI + MACD when enabled.

    `merged_df` may contain only the latest OOS validation fold. `history_df` is therefore
    used for the full Actual timeline when supplied. This keeps the visualization rich
    without contaminating the out-of-sample metrics.
    """
    if forecast_df is None or forecast_df.empty:
        st.warning("Forecast data is not available for plotting.")
        return

    forecast = forecast_df.copy()
    forecast["ds"] = pd.to_datetime(forecast["ds"], errors="coerce").dt.tz_localize(None)
    forecast = forecast.dropna(subset=["ds"]).drop_duplicates("ds", keep="last").sort_values("ds")

    history = _clean_history(history_df, merged_df)

    n_rows = 2 if (show_technicals and tech_df is not None) else 1
    heights = [0.72, 0.28] if n_rows == 2 else [1.0]
    subtitles = [title]
    if n_rows == 2:
        subtitles.append("RSI (14) & MACD")

    fig = make_subplots(
        rows=n_rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=heights,
        subplot_titles=subtitles,
    )

    # --- Full historical Actual price ---
    if not history.empty:
        fig.add_trace(
            go.Scatter(
                x=history["ds"],
                y=history["y"],
                mode="lines",
                name="Actual",
                line=dict(width=2, color="#1d4ed8"),
                hovertemplate="%{x|%Y-%m-%d}<br>Actual: $%{y:,.2f}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    # --- Uncertainty band across historical fit + future projection ---
    if {"yhat_upper", "yhat_lower"}.issubset(forecast.columns):
        fig.add_trace(
            go.Scatter(
                x=forecast["ds"],
                y=forecast["yhat_upper"],
                mode="lines",
                line=dict(width=0),
                showlegend=False,
                hoverinfo="skip",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=forecast["ds"],
                y=forecast["yhat_lower"],
                mode="lines",
                fill="tonexty",
                name="Uncertainty",
                line=dict(width=0),
                fillcolor="rgba(148,163,184,0.28)",
                hoverinfo="skip",
            ),
            row=1,
            col=1,
        )

    # --- One continuous historical-fit + future-forecast line ---
    fig.add_trace(
        go.Scatter(
            x=forecast["ds"],
            y=forecast["yhat"],
            mode="lines",
            name="Forecast",
            line=dict(width=2.2, dash="dash", color="#ef2b2d"),
            hovertemplate="%{x|%Y-%m-%d}<br>Model: $%{y:,.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )

    # --- Historical/future boundary ---
    if not history.empty:
        last_actual = pd.Timestamp(history["ds"].max())
        last_forecast = pd.Timestamp(forecast["ds"].max())

        if last_forecast > last_actual:
            # Subtle future region so the continuation is obvious without breaking the line.
            fig.add_vrect(
                x0=last_actual,
                x1=last_forecast,
                fillcolor="rgba(99,102,241,0.035)",
                line_width=0,
                layer="below",
                row=1,
                col=1,
            )

        fig.add_vline(
            x=last_actual,
            line_dash="dot",
            line_width=2,
            line_color="rgba(100,116,139,0.65)",
            row=1,
            col=1,
        )
        fig.add_annotation(
            x=last_actual,
            y=1.02,
            xref="x",
            yref="paper",
            text="Future forecast →",
            showarrow=False,
            font=dict(size=11, color="#64748b"),
            xanchor="left",
        )

        # Restore the old chart-pattern marker at the forecast boundary.
        if pattern_scores:
            ranked = sorted(
                ((str(k), float(v or 0.0)) for k, v in pattern_scores.items()),
                key=lambda kv: kv[1],
                reverse=True,
            )
            strong = [(k, v) for k, v in ranked if v >= 0.40]
            if strong:
                latest_y = float(history["y"].iloc[-1])
                y_span = max(float(history["y"].max() - history["y"].min()), abs(latest_y) * 0.05, 1.0)
                marker_y = latest_y + 0.10 * y_span
                hover = "<br>".join(f"{name}: {score:.2f}" for name, score in strong[:5])
                fig.add_trace(
                    go.Scatter(
                        x=[last_actual],
                        y=[marker_y],
                        mode="markers",
                        name="Chart Patterns",
                        marker=dict(symbol="diamond", size=13, color="#16a34a", line=dict(width=1, color="#14532d")),
                        hovertemplate=f"<b>Chart Patterns</b><br>{hover}<extra></extra>",
                    ),
                    row=1,
                    col=1,
                )

    # --- Technicals across the full actual history ---
    if n_rows == 2 and tech_df is not None:
        _add_technicals(fig, tech_df, history, row=2)

    fig.update_layout(
        height=520 if n_rows == 1 else 720,
        hovermode="x unified",
        margin=dict(l=10, r=10, t=55, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_yaxes(title_text="Price ($)", row=1, col=1)
    if n_rows == 2:
        fig.update_yaxes(title_text="RSI / MACD", row=2, col=1)
    fig.update_xaxes(title_text="Date", row=n_rows, col=1)

    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Historical red dashes are the fitted model path for visualization. "
        "Reported performance metrics remain rolling out-of-sample results."
    )


def _add_technicals(fig, tech_df, history_df, row):
    """Add RSI + MACD to a subplot row aligned to the full historical timeline."""
    if history_df is None or history_df.empty:
        return

    tech = tech_df.copy()
    if isinstance(tech.columns, pd.MultiIndex):
        tech.columns = [str(c[0]) if isinstance(c, tuple) else str(c) for c in tech.columns]

    date_col = "Date" if "Date" in tech.columns else ("ds" if "ds" in tech.columns else None)
    if date_col is None:
        return

    tech["__ds"] = pd.to_datetime(tech[date_col], errors="coerce").dt.tz_localize(None)
    timeline = pd.DatetimeIndex(history_df["ds"])

    if "RSI_14" in tech.columns:
        rsi = (
            tech[["__ds", "RSI_14"]]
            .dropna()
            .drop_duplicates("__ds")
            .set_index("__ds")["RSI_14"]
        )
        aligned = rsi.reindex(timeline)
        fig.add_trace(
            go.Scatter(x=history_df["ds"], y=aligned, mode="lines", name="RSI (14)", line=dict(color="#14b8a6")),
            row=row,
            col=1,
        )
        fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", annotation_text="Overbought", row=row, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#22c55e", annotation_text="Oversold", row=row, col=1)

    if "MACD_hist" in tech.columns:
        macd = (
            tech[["__ds", "MACD_hist"]]
            .dropna()
            .drop_duplicates("__ds")
            .set_index("__ds")["MACD_hist"]
        )
        aligned = macd.reindex(timeline)
        fig.add_trace(
            go.Bar(x=history_df["ds"], y=aligned, name="MACD Hist", opacity=0.30),
            row=row,
            col=1,
        )


def plot_ensemble(result: dict, ticker: str):
    """Plot ensemble model comparison chart."""
    fig = go.Figure()

    colors = {
        "arima": "#3b82f6",
        "rf": "#f97316",
        "ridge": "#0ea5e9",
        "lstm": "#8b5cf6",
    }
    for name, pred in result["individual"].items():
        fig.add_trace(
            go.Scatter(
                x=result["dates"],
                y=pred,
                mode="lines",
                name=name.upper(),
                line=dict(dash="dot", color=colors.get(name, "gray")),
                opacity=0.7,
            )
        )

    fig.add_trace(
        go.Scatter(
            x=result["dates"],
            y=result["ensemble"],
            mode="lines",
            name="Ensemble",
            line=dict(width=3, color="#16a34a"),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=list(result["dates"]) + list(result["dates"][::-1]),
            y=list(result["upper"]) + list(result["lower"][::-1]),
            fill="toself",
            fillcolor="rgba(22,163,106,0.15)",
            line=dict(color="rgba(0,0,0,0)"),
            name="95% CI",
        )
    )

    fig.update_layout(
        title=f"{ticker} — Ensemble Forecast",
        xaxis_title="Date",
        yaxis_title="Price ($)",
        height=450,
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


def plot_seasonal_bars(analysis: dict):
    """Plot monthly and day-of-week return charts."""
    if "monthly" in analysis and analysis["monthly"]:
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        values = [analysis["monthly"].get(m, 0) * 100 for m in range(1, 13)]
        fig = go.Figure(
            go.Bar(
                x=months,
                y=values,
                marker_color=["#22c55e" if v > 0 else "#ef4444" for v in values],
                text=[f"{v:.2f}%" for v in values],
                textposition="outside",
            )
        )
        fig.update_layout(title="Avg Monthly Returns (%)", yaxis_title="Return %", height=300)
        st.plotly_chart(fig, use_container_width=True)

    if "day_of_week" in analysis and analysis["day_of_week"]:
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        values = [analysis["day_of_week"].get(d, 0) * 100 for d in days]
        fig = go.Figure(
            go.Bar(
                x=days,
                y=values,
                marker_color=["#22c55e" if v > 0 else "#ef4444" for v in values],
                text=[f"{v:.3f}%" for v in values],
                textposition="outside",
            )
        )
        fig.update_layout(title="Avg Returns by Day of Week (%)", yaxis_title="Return %", height=280)
        st.plotly_chart(fig, use_container_width=True)
