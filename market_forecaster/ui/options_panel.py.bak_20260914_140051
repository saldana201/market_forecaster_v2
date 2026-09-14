"""Streamlit panel for Options Flow v2."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from market_forecaster.core.options_flow_v2 import derive_options_regime_overlay, load_options_history


def _pct(value) -> str:
    return "N/A" if value is None else f"{float(value) * 100:.1f}%"


def _score(value) -> str:
    return "N/A" if value is None else f"{float(value):+.2f}"


def render_options_flow_panel(options_data: dict | None, stock_df=None) -> None:
    st.subheader("🧭 Options Flow v2")
    if not options_data:
        st.info("Enable **Options Flow** in the sidebar and run a forecast to load current option-chain analytics.")
        return
    if not options_data.get("available"):
        st.info(options_data.get("reason", "No current option-chain data is available for this ticker."))
        return

    base_regime = None
    if stock_df is not None:
        try:
            from market_forecaster.core.regime import classify_regime
            base_regime = classify_regime(stock_df).composite
        except Exception:
            base_regime = None
    overlay = derive_options_regime_overlay(options_data, base_regime)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        st.metric("Options State", options_data.get("options_state", "N/A"))
    with c2:
        st.metric("Flow Pressure", _score(options_data.get("directional_pressure_score")))
    with c3:
        st.metric("ATM IV", _pct(options_data.get("atm_iv")))
    with c4:
        st.metric("25Δ Skew", _pct(options_data.get("skew_25d")))
    with c5:
        st.metric("IV Term Slope", _pct(options_data.get("iv_term_structure_slope")))
    with c6:
        st.metric("Gamma Balance", _score(options_data.get("gamma_balance_score")))

    st.caption(
        f"Base regime: **{overlay.get('base_regime') or 'N/A'}** · "
        f"Options overlay: **{overlay.get('options_overlay')}** · "
        f"Quote-side pressure coverage: **{options_data.get('pressure_coverage', 0) * 100:.0f}%** "
        f"({options_data.get('pressure_confidence', 'LOW')} confidence)"
    )
    st.warning(
        "GEX is a call-positive / put-negative open-interest proxy, not known dealer positioning. "
        "Directional pressure uses last-price vs bid/ask midpoint as a quote-side proxy, not a true trade aggressor feed."
    )

    buckets = pd.DataFrame(options_data.get("maturity_buckets", []))
    if not buckets.empty:
        display = buckets.copy()
        for col in ("atm_iv", "call_25d_iv", "put_25d_iv", "skew_25d"):
            if col in display.columns:
                display[col] = display[col].map(lambda v: None if pd.isna(v) else round(float(v) * 100, 2))
        for col in ("directional_pressure_score", "pressure_coverage"):
            if col in display.columns:
                display[col] = display[col].map(lambda v: round(float(v), 3))
        cols = [c for c in [
            "bucket", "median_dte", "call_volume", "put_volume", "call_oi", "put_oi",
            "atm_iv", "skew_25d", "directional_pressure_score", "pressure_coverage",
            "signed_gamma_proxy",
        ] if c in display.columns]
        st.markdown("**Maturity buckets**")
        st.dataframe(display[cols], use_container_width=True, hide_index=True)

    unusual = options_data.get("unusual_activity", [])
    if unusual:
        with st.expander(f"Unusual volume/OI candidates ({len(unusual)})"):
            st.dataframe(pd.DataFrame(unusual), use_container_width=True, hide_index=True)

    try:
        history_count = len(load_options_history(options_data.get("ticker", ""), limit=10000))
    except Exception:
        history_count = 0
    st.caption(
        f"Observed snapshots stored locally: **{history_count}**. "
        "These real snapshots will support future historical options validation; no synthetic options history is created."
    )
