"""Drift monitoring + explicit deployment approval UI."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from market_forecaster.core.deployment_policy import (
    approve_champion,
    deployment_policy_state,
    load_governance_events,
)


def render_deployment_policy_panel(ticker: str) -> None:
    st.subheader("🚦 Drift Monitoring & Deployment Policy")
    st.caption(
        "Governance can recommend a challenger, but production changes only after an "
        "explicit approval. Severely degraded challengers are frozen automatically."
    )

    try:
        state = deployment_policy_state(ticker)
    except Exception as exc:
        st.warning(f"Deployment policy unavailable: {exc}")
        return

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Approved Champion", state["approved_champion"])
    with c2:
        st.metric("Effective Champion", state["effective_champion"])
    with c3:
        st.metric("Policy State", state["policy_status"])
    with c4:
        st.metric("Approved Drift", state["approved_drift"].get("status", "COLLECTING"))

    for note in state.get("notes", []):
        st.warning(note)

    drift_df = pd.DataFrame(state["drift"].get("summary", []))
    if not drift_df.empty:
        for col in (
            "recent_mae_bps", "reference_mae_bps", "degradation_pct",
            "recent_direction_pct", "reference_direction_pct", "direction_drop_pp",
        ):
            if col in drift_df.columns:
                drift_df[col] = drift_df[col].map(
                    lambda v: None if pd.isna(v) else round(float(v), 2)
                )
        st.markdown("**Candidate drift monitor**")
        st.dataframe(drift_df, use_container_width=True, hide_index=True)

    segments = pd.DataFrame(state["drift"].get("segments", []))
    if not segments.empty:
        with st.expander("Drift by horizon and market regime"):
            cols = [c for c in [
                "candidate", "horizon", "regime", "status",
                "recent_observations", "reference_observations",
                "recent_mae_bps", "reference_mae_bps", "degradation_pct",
                "recent_direction_pct", "reference_direction_pct", "direction_drop_pp",
            ] if c in segments.columns]
            st.dataframe(segments[cols], use_container_width=True, hide_index=True)

    governance = state["governance"]
    st.caption(
        f"Governance recommendation: **{governance.get('recommendation')}** · "
        f"Observed leader: **{governance.get('observed_leader') or 'Collecting'}**"
    )

    st.markdown("**Explicit champion approval**")
    candidate = st.selectbox(
        "Candidate",
        state["candidate_choices"],
        index=state["candidate_choices"].index(state["approved_champion"])
        if state["approved_champion"] in state["candidate_choices"] else 2,
        key=f"deploy_candidate_{ticker}",
    )
    approved_by = st.text_input(
        "Approved by",
        key=f"deploy_approver_{ticker}",
        placeholder="Name or operator ID",
    )
    rationale = st.text_area(
        "Approval rationale",
        key=f"deploy_rationale_{ticker}",
        placeholder="Why this candidate should become production champion",
    )
    confirm = st.checkbox(
        "I confirm this changes the approved production champion when policy gates allow it.",
        key=f"deploy_confirm_{ticker}",
    )

    if st.button("Approve Production Champion", key=f"deploy_approve_{ticker}", type="primary"):
        if not confirm:
            st.error("Confirmation is required before changing the approved champion.")
        else:
            try:
                event = approve_champion(ticker, candidate, approved_by, rationale)
                st.success(
                    f"Approval recorded: {event['candidate']} · event {event['event_id']}. "
                    "Rerun/open the Ensemble tab to apply the effective champion."
                )
                st.rerun()
            except Exception as exc:
                st.error(f"Approval blocked: {exc}")

    events = load_governance_events(ticker)
    if events:
        with st.expander("Deployment approval history"):
            event_df = pd.DataFrame(events)
            cols = [c for c in [
                "created_at_utc", "event_type", "candidate",
                "approved_by", "rationale", "event_id",
            ] if c in event_df.columns]
            st.dataframe(event_df[cols].tail(50), use_container_width=True, hide_index=True)

    st.warning(
        "The incumbent is never automatically replaced because of drift. "
        "Challenger promotion always requires explicit approval."
    )
