"""Reusable portfolio analytics and Market Explorer-style position cards."""
from __future__ import annotations

import html
from collections import defaultdict

import streamlit as st

from market_forecaster.ui.market_cards import (
    _CATEGORY_ICONS,
    _age_label,
    _fmt_money,
    _fmt_pct,
    _move_class,
    forecast_for_horizon,
    symbol_metadata,
)


def build_portfolio_snapshot(
    positions: list[dict],
    cash: float,
    status_map: dict[str, dict],
    *,
    cost_key: str,
) -> dict:
    rows: list[dict] = []
    holdings_value = 0.0
    gross_exposure = 0.0
    invested_capital = 0.0
    unrealized = 0.0

    for raw in positions:
        ticker = str(raw.get("ticker") or "").upper().strip()
        if not ticker:
            continue
        try:
            quantity = float(raw.get("quantity") or 0.0)
            avg_cost = float(raw.get(cost_key) or 0.0)
        except Exception:
            continue

        status = status_map.get(ticker, {})
        try:
            current_price = float(status.get("current_price"))
        except Exception:
            current_price = None

        signed_market_value = quantity * current_price if current_price is not None else None
        exposure_value = abs(signed_market_value) if signed_market_value is not None else 0.0
        cost_value = abs(quantity * avg_cost)
        row_unrealized = (
            (current_price - avg_cost) * quantity
            if current_price is not None and avg_cost > 0
            else None
        )
        row_return_pct = (
            (row_unrealized / cost_value) * 100.0
            if row_unrealized is not None and cost_value > 0
            else None
        )

        if signed_market_value is not None:
            holdings_value += signed_market_value
            gross_exposure += exposure_value
        invested_capital += cost_value
        if row_unrealized is not None:
            unrealized += row_unrealized

        meta = symbol_metadata(ticker, status)
        rows.append(
            {
                "ticker": ticker,
                "display_name": meta.display_name,
                "category": meta.category,
                "quantity": quantity,
                "avg_cost": avg_cost,
                "current_price": current_price,
                "market_value": signed_market_value,
                "exposure_value": exposure_value,
                "cost_value": cost_value,
                "unrealized": row_unrealized,
                "return_pct": row_return_pct,
                "status": status,
            }
        )

    for row in rows:
        row["allocation_pct"] = (
            (row["exposure_value"] / gross_exposure) * 100.0
            if gross_exposure > 0
            else 0.0
        )

    portfolio_value = float(cash or 0.0) + holdings_value
    return_pct = (
        (unrealized / invested_capital) * 100.0
        if invested_capital > 0
        else 0.0
    )
    cash_pct = (
        (float(cash or 0.0) / portfolio_value) * 100.0
        if portfolio_value > 0
        else 0.0
    )

    sector_values: dict[str, float] = defaultdict(float)
    for row in rows:
        sector_values[row["category"]] += row["exposure_value"]
    sector_allocations = [
        {
            "sector": sector,
            "value": value,
            "allocation_pct": (value / gross_exposure) * 100.0 if gross_exposure > 0 else 0.0,
        }
        for sector, value in sorted(
            sector_values.items(),
            key=lambda item: item[1],
            reverse=True,
        )
    ]

    return {
        "positions": rows,
        "portfolio_value": portfolio_value,
        "holdings_value": holdings_value,
        "gross_exposure": gross_exposure,
        "invested_capital": invested_capital,
        "cash": float(cash or 0.0),
        "cash_pct": cash_pct,
        "unrealized": unrealized,
        "return_pct": return_pct,
        "sector_allocations": sector_allocations,
    }


def render_sector_allocation(snapshot: dict) -> None:
    allocations = snapshot.get("sector_allocations") or []
    if not allocations:
        st.caption("Add positions to see sector allocation.")
        return

    cards: list[str] = []
    for row in allocations:
        pct = max(0.0, min(100.0, float(row.get("allocation_pct") or 0.0)))
        cards.append(
            f"""
<div class="mf-allocation-row">
  <div class="mf-allocation-head">
    <span>{html.escape(str(row.get("sector") or "Other"))}</span>
    <strong>{pct:.1f}%</strong>
  </div>
  <div class="mf-allocation-track">
    <div class="mf-allocation-fill" style="width:{pct:.1f}%"></div>
  </div>
  <div class="mf-allocation-value">{html.escape(_fmt_money(row.get("value")))}</div>
</div>
            """
        )

    st.markdown(
        '<div class="mf-allocation-panel">' + "".join(cards) + "</div>",
        unsafe_allow_html=True,
    )


def render_portfolio_position_card(
    row: dict,
    *,
    horizon_days: int,
    key_prefix: str,
    selected: bool = False,
) -> bool:
    status = row.get("status") or {}
    forecast = forecast_for_horizon(status.get("forecasts") or [], horizon_days)
    expected = forecast.get("expected_return_pct") if forecast else None
    probability = forecast.get("probability_up_pct") if forecast else None
    projected = forecast.get("projected_price") if forecast else None

    probability_value = None
    try:
        probability_value = float(probability)
    except Exception:
        pass
    probability_width = 50 if probability_value is None else max(3, min(100, probability_value))

    pnl = row.get("unrealized")
    pnl_pct = row.get("return_pct")
    pnl_class = _move_class(pnl_pct)
    forecast_class = _move_class(expected)
    selected_class = " mf-market-card-selected" if selected else ""
    selected_tag = '<span class="mf-selected-tag">Selected</span>' if selected else ""
    icon = _CATEGORY_ICONS.get(row.get("category"), str(row.get("ticker") or "•")[:1])
    age = _age_label(status.get("age_hours"))
    direction = "LONG" if float(row.get("quantity") or 0) >= 0 else "SHORT"

    st.markdown(
        f"""
<div class="mf-market-card mf-portfolio-position{selected_class}">
  <div class="mf-card-top">
    <div class="mf-symbol-lockup">
      <div class="mf-symbol-icon">{html.escape(icon)}</div>
      <div>
        <div class="mf-ticker">{html.escape(str(row.get("ticker") or ""))}</div>
        <div class="mf-company">{html.escape(str(row.get("display_name") or row.get("ticker") or ""))}</div>
      </div>
    </div>
    <span class="mf-sector-chip">{html.escape(str(row.get("category") or "Other"))}</span>
  </div>

  <div class="mf-price-row">
    <div>
      <div class="mf-price-label">Market value</div>
      <div class="mf-price">{html.escape(_fmt_money(row.get("market_value")))}</div>
    </div>
    <span class="mf-move {pnl_class}">{html.escape(_fmt_money(pnl))} · {html.escape(_fmt_pct(pnl_pct, signed=True))}</span>
  </div>

  <div class="mf-portfolio-details">
    <div><span>Current</span><strong>{html.escape(_fmt_money(row.get("current_price")))}</strong></div>
    <div><span>Avg cost</span><strong>{html.escape(_fmt_money(row.get("avg_cost")))}</strong></div>
    <div><span>Quantity</span><strong>{abs(float(row.get("quantity") or 0)):,.4f}</strong></div>
    <div><span>Allocation</span><strong>{float(row.get("allocation_pct") or 0):.1f}%</strong></div>
  </div>

  <div class="mf-portfolio-forecast">
    <div>
      <span>{horizon_days}D projected</span>
      <strong>{html.escape(_fmt_money(projected))}</strong>
    </div>
    <span class="mf-move {forecast_class}">{html.escape(_fmt_pct(expected, signed=True))}</span>
  </div>

  <div class="mf-prob-wrap">
    <div class="mf-prob-head">
      <span>Chance of finishing higher</span>
      <strong>{html.escape(_fmt_pct(probability))}</strong>
    </div>
    <div class="mf-prob-track">
      <div class="mf-prob-fill" style="width:{probability_width:.0f}%"></div>
    </div>
  </div>

  <div class="mf-card-footer">
    <span>{direction} · {horizon_days}D outlook</span>
    <span class="mf-ready">{html.escape(age)}</span>
    {selected_tag}
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    return st.button(
        "Viewing forecast" if selected else f"Open {row.get('ticker')} forecast",
        key=f"{key_prefix}_position_{row.get('ticker')}",
        use_container_width=True,
        type="primary" if selected else "secondary",
        disabled=not forecast,
    )
