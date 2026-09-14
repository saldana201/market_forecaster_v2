"""Production Operations dashboard."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from market_forecaster.core.operations import operations_health, run_operations_cycle


def render_operations_panel(ticker: str, stock_df=None) -> None:
    st.subheader("🛠️ Production Operations")
    st.caption(
        "Automatic matured-forecast reconciliation, data/provider health, "
        "execution failures, audit coverage, and drift-policy operations."
    )

    if stock_df is not None and not getattr(stock_df, "empty", True):
        try:
            run_operations_cycle(ticker, stock_df, force=False)
        except Exception as exc:
            st.caption(f"Automatic maintenance unavailable: {exc}")

    try:
        health = operations_health(ticker, stock_df)
    except Exception as exc:
        st.warning(f"Operations health unavailable: {exc}")
        return

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Overall", health["overall_status"])
    with c2: st.metric("Market Data", health["provider_status"])
    with c3: st.metric("Forecast Execution", health["forecast_status"])
    with c4: st.metric("Maintenance", health["maintenance_status"])

    c5, c6, c7, c8 = st.columns(4)
    with c5: st.metric("Data Freshness", health.get("freshness", {}).get("status", "UNKNOWN"))
    with c6: st.metric("Errors (24h)", health["errors_24h"])
    with c7: st.metric("Audited Runs", health["audit"]["runs"])
    with c8: st.metric("Resolved Targets", health["audit"]["resolved_targets"])

    freshness = health.get("freshness", {})
    if freshness:
        st.caption(
            f"Latest market date: {freshness.get('last_market_date') or 'N/A'} · "
            f"Provider: {freshness.get('provider') or 'unknown'} · "
            f"{freshness.get('reason') or ''}"
        )

    dep = health.get("deployment", {})
    st.caption(
        f"Deployment policy: **{dep.get('policy_status', 'UNKNOWN')}** · "
        f"Approved drift: **{dep.get('approved_drift_status', 'UNKNOWN')}** · "
        f"Effective champion: **{dep.get('effective_champion') or 'default/unknown'}**"
    )

    if st.button("Run Operations Maintenance Now", key=f"ops_force_{ticker}"):
        if stock_df is None or getattr(stock_df, "empty", True):
            st.error("Run a forecast first so current market data is available.")
        else:
            try:
                result = run_operations_cycle(ticker, stock_df, force=True)
                st.success(
                    f"Maintenance completed: {result['cycle_status']} · "
                    f"{result['reconciliation'].get('created', 0)} new outcome(s) scored."
                )
                st.rerun()
            except Exception as exc:
                st.error(f"Maintenance failed: {exc}")

    if health.get("errors_7d_by_component"):
        st.markdown("**7-day failures by component**")
        st.dataframe(
            pd.DataFrame([{"Component": k, "Failures": v}
                          for k, v in sorted(health["errors_7d_by_component"].items())]),
            use_container_width=True, hide_index=True,
        )

    events = pd.DataFrame(health.get("recent_events", []))
    if not events.empty:
        with st.expander("Recent operational events"):
            cols = [c for c in ["created_at_utc", "component", "status", "message", "event_id"]
                    if c in events.columns]
            st.dataframe(events[cols].tail(50), use_container_width=True, hide_index=True)

    if health["overall_status"] == "DEGRADED":
        st.error("Production operations are degraded. Review stale data, failures, and drift status.")
    elif health["overall_status"] == "WATCH":
        st.warning("Production operations need attention, but no critical condition is active.")
    elif health["overall_status"] == "COLLECTING":
        st.info("Operations monitoring is initialized and collecting its first maintenance history.")
    else:
        st.success("Production operations are healthy.")
