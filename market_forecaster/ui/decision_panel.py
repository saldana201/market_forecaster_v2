"""Forecast Calibration + Decision Layer UI."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def _price(value):
    return "N/A" if value is None or pd.isna(value) else f"${float(value):,.2f}"


def render_decision_panel(result) -> None:
    st.markdown("---")
    st.subheader("🎯 Calibrated Decision Layer")
    st.caption(
        "Decision support from the governed production champion. "
        "This layer does not alter model routing or deployment."
    )

    if result is None or not getattr(result, "horizons", None):
        st.info("No governed decision result is available yet.")
        return

    primary = next(
        (row for row in result.horizons if row.horizon == result.primary_horizon),
        result.horizons[0],
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Primary", primary.recommendation)
    with c2:
        st.metric("Horizon", f"{primary.horizon} sessions")
    with c3:
        st.metric("Opportunity Score", f"{primary.opportunity_score:.0f}/100")
    with c4:
        prob = primary.probability_up_pct
        st.metric("Probability Up", "Collecting" if prob is None else f"{prob:.1f}%")

    c5, c6, c7, c8 = st.columns(4)
    with c5:
        st.metric("Reference Entry", _price(primary.reference_entry))
    with c6:
        st.metric("Decision Target", _price(primary.decision_target))
    with c7:
        st.metric("Invalidation", _price(primary.invalidation))
    with c8:
        rr = primary.reward_risk
        st.metric("Reward / Risk", "N/A" if rr is None else f"{rr:.2f}x")

    if primary.actionable:
        st.success(
            f"{primary.recommendation}: calibrated evidence and risk gates currently pass "
            f"for the {primary.horizon}-session horizon."
        )
    elif primary.evidence_status == "PROVISIONAL":
        st.info(
            "Decision evidence is PROVISIONAL. The forecast direction is shown for research, "
            "but no calibrated probability or actionable setup is issued yet."
        )
    elif primary.evidence_status == "LOW_SAMPLE":
        st.warning(
            "Decision evidence is LOW_SAMPLE. Probability is shrunk toward 50% and the setup remains research-only."
        )
    else:
        st.info("Calibrated evidence is available, but the current opportunity does not pass all setup gates.")

    rows = []
    for row in result.horizons:
        rows.append({
            "Horizon": f"{row.horizon}D",
            "Evidence": row.evidence_status,
            "Obs": row.resolved_observations,
            "Unique Runs": row.unique_market_snapshots,
            "Direction": row.direction,
            "Raw Return %": round(row.raw_forecast_return_pct, 2),
            "Cal. Expected %": round(row.calibrated_expected_return_pct, 2),
            "P(Up) %": None if row.probability_up_pct is None else round(row.probability_up_pct, 1),
            "Entry": round(row.reference_entry, 2),
            "Target": round(row.decision_target, 2),
            "Invalidation": None if row.invalidation is None else round(row.invalidation, 2),
            "R/R": None if row.reward_risk is None else round(row.reward_risk, 2),
            "Score": round(row.opportunity_score, 1),
            "Recommendation": row.recommendation,
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.caption(
        f"Effective champion: **{result.effective_champion}** · "
        f"Policy: **{result.policy_status}** · Drift: **{result.drift_status}** · "
        f"Data mode: **{result.data_mode}**"
    )

    with st.expander("Decision methodology & safeguards"):
        for note in result.notes:
            st.markdown(f"- {note}")
        st.markdown(
            "- Actionable LONG requires calibrated P(up) ≥58%, expected return ≥1%, "
            "reward/risk ≥1.5x, and opportunity score ≥55."
        )
        st.markdown(
            "- Actionable SHORT requires calibrated P(up) ≤42%, expected return ≤−1%, "
            "reward/risk ≥1.5x, and opportunity score ≥55."
        )
        st.markdown(
            "- Cached data, insufficient calibration evidence, invalid intervals, or severe drift block actionable setups."
        )
