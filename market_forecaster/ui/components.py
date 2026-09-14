"""
Market Forecaster — Reusable UI Components
Signal cards, badges, disclaimers, metric displays.
"""

import streamlit as st
from market_forecaster.config import DISCLAIMER, SIMULATED_DATA_WARNING


# -------------------------------------------------------------------
# Mode constants
# -------------------------------------------------------------------
MODES = ("Simple", "Trader", "Analyst")


def get_mode() -> str:
    return st.session_state.get("app_mode", "Simple")


def is_trader() -> bool:
    return get_mode() in ("Trader", "Analyst")


def is_analyst() -> bool:
    return get_mode() == "Analyst"


# -------------------------------------------------------------------
# Disclaimer
# -------------------------------------------------------------------
def show_disclaimer():
    st.caption(DISCLAIMER)


def show_simulated_warning():
    st.warning(SIMULATED_DATA_WARNING, icon="⚠️")


# -------------------------------------------------------------------
# Signal card
# -------------------------------------------------------------------
def signal_card(signal: str, score: float, confidence: float, label: str = "Trading Signal"):
    """Render a colored signal card."""
    colors = {
        "STRONG BUY": "#15803d", "BUY": "#22c55e",
        "HOLD": "#6b7280",
        "SELL": "#ef4444", "STRONG SELL": "#b91c1c",
    }
    color = colors.get(signal, "#6b7280")

    st.markdown(f"""
    <div style='padding:16px;border-radius:10px;background:{color};
         color:white;text-align:center;margin-bottom:12px;'>
        <div style='font-size:0.85rem;opacity:0.85;'>{label}</div>
        <div style='font-size:1.6rem;font-weight:700;'>{signal}</div>
        <div style='font-size:0.85rem;margin-top:4px;'>
            Score: {score:.2f} · Confidence: {confidence:.0f}%
        </div>
    </div>
    """, unsafe_allow_html=True)


# -------------------------------------------------------------------
# Component score breakdown bar chart
# -------------------------------------------------------------------
def component_breakdown(components: dict):
    """Show a horizontal breakdown of signal component scores."""
    import plotly.graph_objects as go

    if not components:
        return

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=list(components.values()),
        y=list(components.keys()),
        orientation="h",
        marker_color=[
            "#22c55e" if v > 0 else "#ef4444" if v < 0 else "#9ca3af"
            for v in components.values()
        ],
        text=[f"{v:+.2f}" for v in components.values()],
        textposition="outside",
    ))
    fig.update_layout(
        height=max(200, len(components) * 40),
        margin=dict(l=10, r=40, t=10, b=10),
        xaxis=dict(range=[-1.2, 1.2], title="Score"),
        yaxis=dict(autorange="reversed"),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)


# -------------------------------------------------------------------
# Metric row
# -------------------------------------------------------------------
def metric_row(metrics: dict, prefix: str = ""):
    """Render a row of st.metric cards from a dict."""
    cols = st.columns(len(metrics))
    for col, (label, value) in zip(cols, metrics.items()):
        with col:
            if isinstance(value, float):
                st.metric(label, f"{prefix}{value:.2f}")
            else:
                st.metric(label, str(value))


# -------------------------------------------------------------------
# Feature badges
# -------------------------------------------------------------------
def feature_badges(labels: list[str], active: list[bool]):
    """Show a row of green/gray badges."""
    html_parts = []
    for label, on in zip(labels, active):
        bg = "#dcfce7" if on else "#e5e7eb"
        fg = "#166534" if on else "#6b7280"
        html_parts.append(
            f"<span style='background:{bg};color:{fg};"
            f"padding:2px 10px;border-radius:999px;font-size:0.8rem;"
            f"margin-right:4px;'>{label}</span>"
        )
    st.markdown("".join(html_parts), unsafe_allow_html=True)


# -------------------------------------------------------------------
# Model availability indicators
# -------------------------------------------------------------------
def model_availability_badges():
    from market_forecaster.core.ensemble import ARIMA_AVAILABLE, LSTM_AVAILABLE
    c1, c2, c3 = st.columns(3)
    with c1:
        st.caption(f"ARIMA: {'✅' if ARIMA_AVAILABLE else '❌'}")
    with c2:
        st.caption(f"LSTM: {'✅' if LSTM_AVAILABLE else '❌'}")
    with c3:
        st.caption("Prophet: ✅ | RF: ✅")
