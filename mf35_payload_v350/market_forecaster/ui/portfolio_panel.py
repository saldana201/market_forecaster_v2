"""Portfolio state + position-aware ranking UI."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from market_forecaster.core.opportunity_ranking import load_ranking_snapshot
from market_forecaster.core.portfolio import (
    build_portfolio_aware_ranking,
    load_portfolio_overlay,
    load_portfolio_state,
    save_portfolio_state,
)


def _money(value):
    if value is None or pd.isna(value):
        return None
    return f"${float(value):,.2f}"


def render_portfolio_panel() -> None:
    st.subheader("💼 Portfolio State & Position-Aware Ranking")
    st.caption(
        "Manual local portfolio state. Existing exposure can reduce new research "
        "allocation, but v3.5 never places or resizes trades automatically."
    )

    state = load_portfolio_state()
    cash = st.number_input(
        "Cash / unallocated capital",
        min_value=0.0,
        value=float(state.get("cash", 0.0) or 0.0),
        step=100.0,
        key="portfolio_cash",
    )

    positions = pd.DataFrame(
        state.get("positions", []),
        columns=["ticker", "quantity", "cost_basis"],
    )
    edited = st.data_editor(
        positions,
        num_rows="dynamic",
        use_container_width=True,
        key="portfolio_positions_editor",
        column_config={
            "ticker": st.column_config.TextColumn("Ticker"),
            "quantity": st.column_config.NumberColumn(
                "Quantity (+ long / − short)",
                format="%.4f",
            ),
            "cost_basis": st.column_config.NumberColumn(
                "Average Cost Basis",
                min_value=0.0,
                format="$%.2f",
            ),
        },
    )

    if st.button("Save Portfolio State", key="portfolio_save"):
        try:
            rows = []
            for record in edited.to_dict("records"):
                ticker = str(record.get("ticker", "") or "").strip()
                qty = record.get("quantity")
                cost = record.get("cost_basis")
                if not ticker and (qty is None or pd.isna(qty)):
                    continue
                rows.append({
                    "ticker": ticker,
                    "quantity": qty,
                    "cost_basis": cost,
                })
            saved = save_portfolio_state(cash, rows)
            st.success(f"Saved {len(saved['positions'])} position(s).")
            st.rerun()
        except Exception as exc:
            st.error(f"Portfolio save failed: {exc}")

    c1, c2, c3 = st.columns(3)
    with c1:
        max_position = st.slider(
            "Max single-name exposure %",
            min_value=5,
            max_value=40,
            value=20,
            step=5,
            key="portfolio_max_position",
        )
    with c2:
        max_cluster = st.slider(
            "Max correlated cluster %",
            min_value=15,
            max_value=70,
            value=40,
            step=5,
            key="portfolio_max_cluster",
        )
    with c3:
        correlation_threshold = st.slider(
            "Correlation threshold",
            min_value=0.50,
            max_value=0.90,
            value=0.70,
            step=0.05,
            key="portfolio_corr_threshold",
        )

    if st.button(
        "Build Position-Aware Ranking",
        type="primary",
        key="portfolio_rank",
    ):
        base = load_ranking_snapshot()
        if not base:
            st.error("Run the 3.4 watchlist ranking first.")
        else:
            with st.spinner("Valuing positions and applying portfolio exposure controls..."):
                try:
                    result = build_portfolio_aware_ranking(
                        base,
                        load_portfolio_state(),
                        max_position_pct=float(max_position),
                        max_correlated_cluster_pct=float(max_cluster),
                        correlation_threshold=float(correlation_threshold),
                    )
                    st.session_state["portfolio_overlay"] = result
                except Exception as exc:
                    st.error(f"Position-aware ranking failed: {exc}")

    result = st.session_state.get("portfolio_overlay") or load_portfolio_overlay()
    if not result:
        st.info(
            "Save portfolio state, run the 3.4 watchlist ranking, then build the "
            "position-aware ranking."
        )
        return

    summary = result.get("portfolio_summary", {})
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Capital Base", _money(summary.get("capital_base")) or "N/A")
    with c2:
        st.metric("Gross Exposure", _money(summary.get("gross_exposure")) or "N/A")
    with c3:
        st.metric("Unrealized P/L", _money(summary.get("total_unrealized_pl")) or "N/A")
    with c4:
        st.metric(
            "Unallocated Research Budget",
            f"{float(result.get('unallocated_portfolio_research_budget_pct', 100.0)):.1f}%",
        )

    c5, c6, c7 = st.columns(3)
    with c5:
        st.metric("Cash Weight", f"{float(summary.get('cash_weight_pct', 0.0)):.1f}%")
    with c6:
        st.metric("Long Exposure", f"{float(summary.get('long_exposure_pct', 0.0)):.1f}%")
    with c7:
        st.metric("Short Exposure", f"{float(summary.get('short_exposure_pct', 0.0)):.1f}%")

    for alert in result.get("alerts", []):
        if alert.get("type") == "INVALIDATION":
            st.error(alert.get("message"))
        else:
            st.warning(alert.get("message"))

    positions = result.get("positions", [])
    if positions:
        with st.expander("Current position health", expanded=True):
            rows = []
            for row in positions:
                rows.append({
                    "Ticker": row.get("ticker"),
                    "Side": row.get("side"),
                    "Quantity": row.get("quantity"),
                    "Cost Basis": row.get("cost_basis"),
                    "Price": row.get("current_price"),
                    "Weight %": round(float(row.get("portfolio_weight_pct", 0.0)), 1),
                    "Unrealized P/L": row.get("unrealized_pl"),
                    "Unrealized P/L %": None if row.get("unrealized_pl_pct") is None else round(float(row["unrealized_pl_pct"]), 1),
                    "Decision": row.get("decision_recommendation"),
                    "Invalidation": row.get("invalidation"),
                    "Invalidation Breached": row.get("invalidation_breached"),
                    "Price Source": row.get("price_source"),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    ranked = result.get("ranked", [])
    if ranked:
        rows = []
        for row in ranked:
            rows.append({
                "Rank": row.get("portfolio_rank"),
                "Ticker": row.get("ticker"),
                "Portfolio Action": row.get("portfolio_action"),
                "3.4 Recommendation": row.get("recommendation"),
                "Evidence": row.get("evidence_status"),
                "3.4 Rank Score": round(float(row.get("ranking_score", 0.0)), 1),
                "Portfolio Rank Score": round(float(row.get("portfolio_ranking_score", 0.0)), 1),
                "Existing Weight %": round(float(row.get("current_position_weight_pct", 0.0)), 1),
                "Correlated Exposure %": round(float(row.get("correlated_existing_exposure_pct", 0.0)), 1),
                "Single-Name Headroom %": round(float(row.get("single_name_headroom_pct", 0.0)), 1),
                "Cluster Headroom %": round(float(row.get("correlated_cluster_headroom_pct", 0.0)), 1),
                "3.4 Research Budget %": round(float(row.get("research_risk_budget_pct", 0.0)), 1),
                "Portfolio Research Budget %": round(float(row.get("portfolio_research_budget_pct", 0.0)), 1),
                "Position Conflict": row.get("position_conflict"),
                "Invalidation Breached": row.get("invalidation_breached"),
            })
        st.markdown("**Position-aware opportunity ranking**")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with st.expander("Portfolio overlay methodology"):
        for note in result.get("notes", []):
            st.markdown(f"- {note}")
        st.markdown(
            "- A position at or above the single-name limit receives severe concentration penalty and zero/limited new headroom."
        )
        st.markdown(
            "- Correlated same-direction holdings consume cluster headroom before a new allocation is suggested."
        )
        st.markdown(
            "- `EXIT_REVIEW` and `POSITION_CONFLICT` are review flags, not automated orders."
        )
