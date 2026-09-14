"""Forecast Audit + Champion/Challenger governance UI."""
from __future__ import annotations

import json
import pandas as pd
import streamlit as st

from market_forecaster.core.forecast_audit import audit_snapshot, reconcile_matured_outcomes


def render_governance_panel(ticker: str, stock_df=None) -> None:
    st.subheader("🧾 Forecast Audit & Champion/Challenger")
    st.caption(
        "Production forecasts are recorded before outcomes are known. "
        "Realized prices are scored later in a separate append-only outcome ledger."
    )

    try:
        snapshot = audit_snapshot(ticker)
    except Exception as exc:
        st.warning(f"Forecast audit unavailable: {exc}")
        return

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Audited Runs", snapshot["runs"])
    with c2:
        st.metric("Forecast Targets", snapshot["targets"])
    with c3:
        st.metric("Resolved", snapshot["resolved_targets"])
    with c4:
        st.metric("Pending", snapshot["pending_targets"])

    if snapshot["runs"] == 0:
        st.info(
            "Run a forecast with Ensemble enabled. Once Production Consensus is calculated, "
            "the run will be added to the audit ledger automatically."
        )
        return

    if stock_df is not None and not getattr(stock_df, "empty", True):
        if st.button("Score Matured Forecasts", key=f"audit_reconcile_{ticker}"):
            with st.spinner("Scoring forecast targets whose market dates have matured..."):
                try:
                    result = reconcile_matured_outcomes(ticker, stock_df)
                    st.success(
                        f"Outcome reconciliation complete: {result['created']} new outcome(s), "
                        f"{result['pending']} target(s) still pending."
                    )
                    snapshot = audit_snapshot(ticker)
                except Exception as exc:
                    st.error(f"Outcome reconciliation failed: {exc}")
    else:
        st.info("Run a forecast first so current market data is available for outcome scoring.")

    governance = snapshot["governance"]
    g1, g2, g3 = st.columns(3)
    with g1:
        st.metric("Governance State", governance.get("status", "COLLECTING"))
    with g2:
        st.metric("Observed Leader", governance.get("observed_leader") or "Collecting")
    with g3:
        st.metric("Recommendation", governance.get("recommendation", "COLLECT"))

    leaderboard = pd.DataFrame(governance.get("leaderboard", []))
    if not leaderboard.empty:
        for col in ("mae_return_bps", "median_abs_return_error_bps", "price_mape_pct", "directional_accuracy_pct"):
            if col in leaderboard.columns:
                leaderboard[col] = leaderboard[col].map(
                    lambda v: None if pd.isna(v) else round(float(v), 2)
                )
        st.markdown("**Realized performance leaderboard**")
        st.dataframe(leaderboard, use_container_width=True, hide_index=True)
        st.caption(
            f"Eligibility requires at least {governance['minimum_observations']} resolved predictions "
            f"across {governance['minimum_unique_runs']} unique market snapshots."
        )
    else:
        st.info("No forecast targets have matured yet. Governance remains in evidence-collection mode.")

    if governance.get("status") == "CHALLENGER_LEADS":
        improvement = governance.get("improvement_vs_incumbent_pct")
        text = "N/A" if improvement is None else f"{float(improvement):.1f}%"
        st.warning(
            f"A challenger is outperforming the incumbent by about {text} on realized return error. "
            "v2.9 recommends review only; it does not auto-promote."
        )
    elif governance.get("status") == "INCUMBENT_LEADS":
        st.success("The adaptive production consensus currently leads eligible challengers.")

    recent = pd.DataFrame(snapshot.get("recent_runs", []))
    if not recent.empty:
        with st.expander("Recent audited forecast runs"):
            cols = [c for c in [
                "created_at_utc", "market_last_timestamp", "app_version",
                "production_status", "base_status", "current_regime",
                "options_promotion_status", "run_id",
            ] if c in recent.columns]
            st.dataframe(recent[cols].tail(20), use_container_width=True, hide_index=True)

    export = {
        "ticker": snapshot["ticker"],
        "governance": governance,
        "recent_runs": snapshot.get("recent_runs", []),
        "recent_outcomes": snapshot.get("recent_outcomes", []),
    }
    st.download_button(
        "Download Audit Snapshot (JSON)",
        data=json.dumps(export, indent=2, default=str),
        file_name=f"{str(ticker).upper()}_forecast_audit.json",
        mime="application/json",
        key=f"audit_download_{ticker}",
    )

    st.warning(
        "Governance is advisory in v2.9. No challenger is automatically promoted and "
        "no incumbent is automatically demoted from realized outcomes alone."
    )
