"""Persistent Forecast Contract history for authenticated accounts."""
from __future__ import annotations

import streamlit as st

from market_forecaster.core.entitlements import can_save_forecast_history
from market_forecaster.core.session_identity import resolve_identity
from market_forecaster.persistence.supabase_data import PersistenceError
from market_forecaster.services.user_data import (
    client_for_state,
    delete_saved_forecast,
    list_saved_forecasts,
)


def _money(value) -> str:
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "—"


def _percent(value) -> str:
    try:
        return f"{float(value):+.1f}%"
    except Exception:
        return "—"


def _anchor_forecast(contract: dict) -> dict:
    rows = contract.get("forecasts") or []
    by_horizon = {
        int(row.get("horizon_days", -1)): row
        for row in rows
        if isinstance(row, dict)
    }
    for horizon in (10, 5, 20, 1):
        if horizon in by_horizon:
            return by_horizon[horizon]
    return rows[0] if rows else {}


def render_forecast_history() -> None:
    identity = resolve_identity(st.session_state)

    st.markdown("## Forecast History")
    st.caption(
        "Saved canonical Forecast Contracts stay attached to your account so you can "
        "review what the platform showed at an earlier point in time."
    )

    if not can_save_forecast_history(identity):
        st.info("Persistent forecast history requires an active Standard or Pro plan.")
        return

    try:
        client = client_for_state(st.session_state, identity)
        rows = list_saved_forecasts(client, identity, limit=50)
    except PersistenceError as exc:
        st.warning(f"Forecast history is temporarily unavailable: {exc}")
        return

    if not rows:
        with st.container(border=True):
            st.markdown("### No saved forecasts yet")
            st.caption(
                "Open the Forecast tab and choose **Save Forecast to History**. "
                "Saving is idempotent, so the same Forecast Contract is stored only once."
            )
        return

    st.metric("Saved forecasts", len(rows))

    for row in rows:
        contract = row.get("forecast_contract")
        if not isinstance(contract, dict):
            continue

        ticker = str(row.get("ticker") or contract.get("ticker") or "").upper()
        anchor = _anchor_forecast(contract)
        generated = str(
            row.get("generated_at")
            or contract.get("generated_at")
            or row.get("created_at")
            or ""
        )

        with st.container(border=True):
            h1, h2, h3, h4 = st.columns([1.1, 1.2, 1.2, 1.5])
            with h1:
                st.markdown(f"### {ticker}")
            with h2:
                st.metric("Saved price", _money(contract.get("current_price")))
            with h3:
                st.metric(
                    "Primary projection",
                    _money(anchor.get("projected_price")),
                    delta=_percent(anchor.get("expected_return_pct")),
                )
            with h4:
                st.caption(f"Generated: {generated[:19].replace('T', ' ')} UTC")
                st.caption(f"Contract: {str(row.get('contract_id') or contract.get('contract_id') or '')[:16]}")

            c1, c2 = st.columns(2)
            with c1:
                if st.button(
                    "Load this saved forecast",
                    key=f"history_load_{row.get('id')}",
                    use_container_width=True,
                    type="primary",
                ):
                    st.session_state["simple_forecast_contract"] = contract
                    st.session_state["ticker"] = ticker
                    st.success(
                        f"Loaded the saved {ticker} contract. Open the Forecast tab to review it."
                    )
            with c2:
                if st.button(
                    "Delete from history",
                    key=f"history_delete_{row.get('id')}",
                    use_container_width=True,
                ):
                    try:
                        delete_saved_forecast(
                            client,
                            identity,
                            str(row.get("id") or ""),
                        )
                        st.rerun()
                    except PersistenceError as exc:
                        st.error(f"Could not delete saved forecast: {exc}")
