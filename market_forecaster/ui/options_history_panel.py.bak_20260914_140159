"""Streamlit panel for Historical Options Intelligence 2.7."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from market_forecaster.core.historical_options import (
    MIN_UNIQUE_SESSIONS,
    evaluate_options_history,
    flatten_options_history,
)
from market_forecaster.core.options_flow_v2 import load_options_history


def _bps(value) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value) * 10000:.1f}"


def render_options_history_panel(ticker: str, stock_df=None) -> None:
    st.subheader("🧪 Historical Options Intelligence")
    st.caption(
        "Validates only real observed Options Flow v2 snapshots. "
        "No synthetic options history is generated."
    )
    try:
        history = load_options_history(ticker, limit=10000)
    except Exception as exc:
        st.warning(f"Unable to load options snapshot history: {exc}")
        return

    flattened = flatten_options_history(history)
    unique_sessions = len(flattened)
    progress = min(1.0, unique_sessions / max(MIN_UNIQUE_SESSIONS, 1))
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Unique Sessions", f"{unique_sessions}/{MIN_UNIQUE_SESSIONS}")
    with c2:
        first = flattened["session_date"].min() if not flattened.empty else None
        st.metric("First Snapshot", "N/A" if first is None else pd.Timestamp(first).date().isoformat())
    with c3:
        last = flattened["session_date"].max() if not flattened.empty else None
        st.metric("Latest Snapshot", "N/A" if last is None else pd.Timestamp(last).date().isoformat())

    st.progress(progress)
    st.caption(
        "Only the latest real snapshot per New York market session counts. "
        "Running the app repeatedly on the same day does not manufacture more history."
    )

    if stock_df is None or getattr(stock_df, "empty", True):
        st.info("Run a forecast first so historical price data is available for validation.")
        return
    if unique_sessions < MIN_UNIQUE_SESSIONS:
        st.info(
            f"Collecting history. Validation arms at {MIN_UNIQUE_SESSIONS} unique sessions; "
            f"{MIN_UNIQUE_SESSIONS - unique_sessions} more are needed."
        )
        return

    if st.button("Run Historical Options Validation", key=f"options_history_validate_{ticker}"):
        with st.spinner("Running embargoed options walk-forward validation..."):
            try:
                st.session_state["options_history_validation"] = evaluate_options_history(history, stock_df)
            except Exception as exc:
                st.error(f"Historical options validation failed: {exc}")

    result = st.session_state.get("options_history_validation")
    if not result or result.get("ticker") not in (None, str(ticker).upper()):
        return
    horizons = pd.DataFrame(result.get("horizons", []))
    if horizons.empty:
        st.info(result.get("reason", "No validation result available."))
        return

    display = horizons.copy()
    display["Model MAE (bps)"] = display["model_mae"].map(_bps)
    display["Baseline MAE (bps)"] = display["baseline_mae"].map(_bps)
    display["Improvement %"] = display["improvement_pct"].map(
        lambda v: None if v is None or pd.isna(v) else round(float(v), 2)
    )
    display["Direction %"] = display["directional_accuracy"].map(
        lambda v: None if v is None or pd.isna(v) else round(float(v), 1)
    )
    display["Fold Win %"] = display["fold_win_rate"].map(
        lambda v: None if v is None or pd.isna(v) else round(float(v) * 100, 1)
    )
    cols = [
        "horizon", "samples", "oos_predictions", "folds",
        "Model MAE (bps)", "Baseline MAE (bps)", "Improvement %",
        "Direction %", "Fold Win %", "gate", "reason",
    ]
    st.dataframe(display[[c for c in cols if c in display.columns]], use_container_width=True, hide_index=True)

    passes = result.get("promotion_candidates", [])
    if passes:
        st.success(
            "Research promotion candidate horizon(s): "
            + ", ".join(f"{h}D" for h in passes)
            + ". They still do NOT alter routing in v2.7."
        )
    else:
        st.info("No options horizon has passed the promotion gate yet.")

    selected = st.selectbox(
        "Feature rank-IC horizon",
        options=[int(h) for h in horizons["horizon"].tolist()],
        key=f"options_ic_horizon_{ticker}",
    )
    match = next((r for r in result["horizons"] if int(r["horizon"]) == int(selected)), None)
    ic_rows = (match or {}).get("feature_ic", [])
    if ic_rows:
        st.markdown("**Descriptive feature rank correlation**")
        st.dataframe(pd.DataFrame(ic_rows), use_container_width=True, hide_index=True)
        st.caption(
            "Rank IC is descriptive only and uses the available aligned sample. "
            "It is not used to pass the production gate."
        )

    st.warning(
        "2.7 is validation-only. Options features cannot change Regime routing or "
        "Production Consensus until a later promotion release explicitly validates that integration."
    )
