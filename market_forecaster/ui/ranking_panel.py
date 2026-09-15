"""Multi-ticker opportunity ranking UI."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from market_forecaster.core.opportunity_ranking import (
    load_ranking_snapshot,
    load_watchlist,
    rank_watchlist,
    save_watchlist,
)


def render_opportunity_ranking_panel(current_ticker: str) -> None:
    st.subheader("🏁 Multi-Ticker Opportunity Ranking")
    st.caption(
        "Ranks existing governed 3.3 decision snapshots. "
        "This scanner does not silently run forecast models across the watchlist."
    )

    stored = load_watchlist(default=[current_ticker])
    default_text = ", ".join(stored or [current_ticker])
    watchlist_text = st.text_input(
        "Watchlist",
        value=default_text,
        key="opportunity_watchlist_text",
        help="Comma-separated symbols. Maximum 30.",
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        include_corr = st.checkbox(
            "Correlation diversification",
            value=True,
            key="opportunity_use_corr",
        )
    with c2:
        max_weight = st.slider(
            "Max research risk budget / symbol",
            min_value=5,
            max_value=30,
            value=25,
            step=5,
            key="opportunity_max_weight",
        )
    with c3:
        if st.button("Save Watchlist", key="opportunity_save_watchlist"):
            symbols = save_watchlist(watchlist_text)
            st.success(f"Saved {len(symbols)} ticker(s).")

    if st.button("Rank Watchlist", type="primary", key="opportunity_rank"):
        with st.spinner("Ranking governed decision snapshots..."):
            try:
                result = rank_watchlist(
                    watchlist_text,
                    include_correlation=include_corr,
                    max_single_risk_budget_pct=float(max_weight),
                )
                st.session_state["opportunity_ranking"] = result
            except Exception as exc:
                st.error(f"Opportunity ranking failed: {exc}")

    result = st.session_state.get("opportunity_ranking") or load_ranking_snapshot()
    if not result:
        st.info("Run at least one governed Ensemble forecast, then rank the watchlist.")
        return

    ranked = result.get("ranked", [])
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Decision Coverage", f"{result.get('coverage_count', 0)}/{len(result.get('watchlist', []))}")
    with c2:
        st.metric("Calibrated", result.get("calibrated_count", 0))
    with c3:
        st.metric("Actionable", result.get("actionable_count", 0))
    with c4:
        st.metric(
            "Unallocated Research Budget",
            f"{float(result.get('unallocated_research_risk_budget_pct', 100.0)):.1f}%",
        )

    if result.get("missing_decisions"):
        st.warning(
            "No governed 3.3 decision snapshot yet for: "
            + ", ".join(result["missing_decisions"])
            + ". Run a normal Ensemble forecast for those symbols first."
        )

    if ranked:
        rows = []
        for row in ranked:
            rows.append({
                "Rank": row.get("rank"),
                "Ticker": row.get("ticker"),
                "Horizon": f"{row.get('horizon')}D",
                "Recommendation": row.get("recommendation"),
                "Evidence": row.get("evidence_status"),
                "Actionable": row.get("actionable"),
                "Opportunity": round(float(row.get("opportunity_score", 0.0)), 1),
                "Rank Score": round(float(row.get("ranking_score", 0.0)), 1),
                "Expected %": round(float(row.get("expected_return_pct", 0.0)), 2),
                "P(Up) %": None if row.get("probability_up_pct") is None else round(float(row["probability_up_pct"]), 1),
                "R/R": None if row.get("reward_risk") is None else round(float(row["reward_risk"]), 2),
                "Data": row.get("data_mode"),
                "Drift": row.get("drift_status"),
                "Age h": None if row.get("decision_age_hours") is None else round(float(row["decision_age_hours"]), 1),
                "Max Same-Dir Corr": None if row.get("max_same_direction_correlation") is None else round(float(row["max_same_direction_correlation"]), 2),
                "Corr Penalty %": round(float(row.get("correlation_penalty_pct", 0.0)), 1),
                "Research Risk Budget %": round(float(row.get("research_risk_budget_pct", 0.0)), 1),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        top = ranked[0]
        st.caption(
            f"Current top-ranked snapshot: **{top['ticker']}** · "
            f"{top['recommendation']} · ranking score **{float(top['ranking_score']):.1f}**."
        )

    matrix = result.get("correlation_matrix") or {}
    if matrix:
        with st.expander("Return correlation matrix"):
            corr_df = pd.DataFrame(matrix)
            st.dataframe(corr_df.round(2), use_container_width=True)

    with st.expander("Ranking methodology"):
        for note in result.get("notes", []):
            st.markdown(f"- {note}")
        st.markdown(
            "- Correlation penalty starts only above +0.60 for same-direction names and reaches a maximum 25% score penalty at +1.00."
        )
        st.markdown(
            "- Highly correlated same-direction names (≥0.85) have their research risk-budget cap reduced to 15%."
        )
