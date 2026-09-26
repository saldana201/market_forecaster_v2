"""Persistent Forecast Contract history for authenticated accounts."""
from __future__ import annotations

import html

import streamlit as st

from market_forecaster.core.entitlements import can_save_forecast_history
from market_forecaster.core.session_identity import resolve_identity
from market_forecaster.persistence.supabase_data import PersistenceError
from market_forecaster.services.user_data import (
    client_for_state,
    delete_saved_forecast,
    list_saved_forecasts,
)
from market_forecaster.ui.design_system import (
    render_kpi_strip,
    render_page_header,
    render_section_header,
)
from market_forecaster.ui.market_cards import (
    forecast_for_horizon,
    render_horizon_selector,
)


def _money(value) -> str:
    try:
        return "$" + f"{float(value):,.2f}"
    except Exception:
        return "—"


def _percent(value, *, signed: bool = True) -> str:
    try:
        number = float(value)
        return f"{number:+.1f}%" if signed else f"{number:.0f}%"
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


def _generated_label(row: dict, contract: dict) -> str:
    generated = str(
        row.get("generated_at")
        or contract.get("generated_at")
        or row.get("created_at")
        or ""
    )
    return generated[:19].replace("T", " ") if generated else "Unknown"


def _render_history_card(
    *,
    row: dict,
    contract: dict,
    ticker: str,
    horizon_days: int,
) -> None:
    forecast = forecast_for_horizon(contract.get("forecasts") or [], horizon_days)
    if forecast is None:
        forecast = _anchor_forecast(contract)

    expected = forecast.get("expected_return_pct")
    try:
        move_value = float(expected)
    except Exception:
        move_value = 0.0
    move_class = "mf-move-up" if move_value > 0.05 else "mf-move-down" if move_value < -0.05 else "mf-move-flat"

    probability = forecast.get("probability_up_pct")
    try:
        prob_value = max(3.0, min(100.0, float(probability)))
    except Exception:
        prob_value = 50.0

    used_horizon = forecast.get("horizon_days") or horizon_days
    contract_id = str(row.get("contract_id") or contract.get("contract_id") or "")
    generated = _generated_label(row, contract)

    st.markdown(
        f"""
<div class="mf-market-card">
  <div class="mf-card-top">
    <div class="mf-symbol-lockup">
      <div class="mf-symbol-icon">H</div>
      <div>
        <div class="mf-ticker">{html.escape(ticker)}</div>
        <div class="mf-company">Saved Forecast Contract</div>
      </div>
    </div>
    <span class="mf-sector-chip">{html.escape(str(used_horizon))}D history</span>
  </div>

  <div class="mf-price-row">
    <div>
      <div class="mf-price-label">Saved market price</div>
      <div class="mf-price">{html.escape(_money(contract.get("current_price")))}</div>
    </div>
    <span class="mf-move {move_class}">{html.escape(_percent(expected))}</span>
  </div>

  <div class="mf-price-row" style="margin-top:.25rem">
    <div>
      <div class="mf-price-label">Projected price</div>
      <div style="font-weight:800;font-size:1.05rem">{html.escape(_money(forecast.get("projected_price")))}</div>
    </div>
    <div class="mf-price-label">Generated {html.escape(generated)} UTC</div>
  </div>

  <div class="mf-prob-wrap">
    <div class="mf-prob-head">
      <span>Chance of finishing higher</span>
      <strong>{html.escape(_percent(probability, signed=False))}</strong>
    </div>
    <div class="mf-prob-track">
      <div class="mf-prob-fill" style="width:{prob_value:.0f}%"></div>
    </div>
  </div>

  <div class="mf-card-footer">
    <span>Contract snapshot</span>
    <span class="mf-ready">{html.escape(contract_id[:16] or "Saved")}</span>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_forecast_history() -> None:
    identity = resolve_identity(st.session_state)

    render_page_header(
        "Forecast History",
        "Revisit saved Forecast Contracts with the same multi-horizon view used across Market Explorer.",
        eyebrow="Account workspace",
        badge=f"{identity.plan.title()} · Persistent",
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

    unique_tickers = {
        str(row.get("ticker") or "").upper()
        for row in rows
        if str(row.get("ticker") or "").strip()
    }
    render_kpi_strip(
        [
            {
                "label": "Saved forecasts",
                "value": str(len(rows)),
                "caption": "Canonical contracts stored on your account",
                "tone": "accent",
            },
            {
                "label": "Markets",
                "value": str(len(unique_tickers)),
                "caption": "Unique symbols represented in history",
            },
            {
                "label": "Storage",
                "value": "Persistent",
                "caption": "Available across sessions and devices",
                "tone": "positive",
            },
        ]
    )

    if not rows:
        with st.container(border=True):
            st.markdown("### No saved forecasts yet")
            st.caption(
                "Open Forecast and choose **Save Forecast to History**. "
                "Saving is idempotent, so the same Forecast Contract is stored only once."
            )
        return

    selector_left, selector_right = st.columns([2, 5])
    with selector_left:
        render_section_header("Forecast horizon", "Apply one horizon across all saved cards")
        horizon_days = render_horizon_selector(key="history_horizon")
    with selector_right:
        st.caption(
            "Switch between 1D, 5D, 10D, and 20D to compare what each saved contract projected at that point in time."
        )

    render_section_header(
        "Saved contracts",
        f"{len(rows)} historical snapshot{'s' if len(rows) != 1 else ''}",
        badge="Newest first",
    )

    for row in rows:
        contract = row.get("forecast_contract")
        if not isinstance(contract, dict):
            continue

        ticker = str(row.get("ticker") or contract.get("ticker") or "").upper()
        _render_history_card(
            row=row,
            contract=contract,
            ticker=ticker,
            horizon_days=horizon_days,
        )

        c1, c2 = st.columns([2.2, 1])
        with c1:
            if st.button(
                f"Open saved {ticker} forecast",
                key=f"history_load_{row.get('id')}",
                use_container_width=True,
                type="primary",
            ):
                st.session_state["simple_forecast_contract"] = contract
                st.session_state["ticker"] = ticker
                st.query_params["view"] = "forecast"
                st.success(f"Loaded the saved {ticker} contract.")
                st.rerun()
        with c2:
            if st.button(
                "Delete",
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
