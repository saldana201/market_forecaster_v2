"""Reusable Market Explorer-style cards for watchlists."""
from __future__ import annotations

import html
from dataclasses import dataclass

import streamlit as st

from market_forecaster.core.demo_universe import demo_symbols


_CATEGORY_ICONS = {
    "Technology": "T",
    "Financials": "$",
    "Healthcare": "+",
    "Energy": "E",
    "Consumer": "C",
    "Industrials": "I",
    "Broad Market": "M",
    "Other": "•",
}

SECTOR_ORDER = (
    "Technology",
    "Financials",
    "Healthcare",
    "Energy",
    "Consumer",
    "Industrials",
    "Broad Market",
    "Other",
)


@dataclass(frozen=True)
class WatchlistSymbolMeta:
    ticker: str
    display_name: str
    category: str


def _number(value):
    try:
        return float(value)
    except Exception:
        return None


def _fmt_money(value) -> str:
    value = _number(value)
    return "—" if value is None else "$" + f"{value:,.2f}"


def _fmt_pct(value, *, signed: bool = False) -> str:
    value = _number(value)
    if value is None:
        return "—"
    return f"{value:+.1f}%" if signed else f"{value:.0f}%"


def _move_class(expected) -> str:
    value = _number(expected)
    if value is None or abs(value) < 0.05:
        return "mf-move-flat"
    return "mf-move-up" if value > 0 else "mf-move-down"


def _age_label(age_hours) -> str:
    value = _number(age_hours)
    if value is None:
        return "Cached"
    if value < 1:
        return "Updated <1h ago"
    if value < 24:
        return f"Updated {int(value)}h ago"
    return f"Updated {int(value // 24)}d ago"


def forecast_for_horizon(forecasts: list[dict], horizon_days: int) -> dict | None:
    for row in forecasts or []:
        try:
            if int(row.get("horizon_days", -1)) == int(horizon_days):
                return row
        except Exception:
            continue
    return None


def symbol_metadata(ticker: str, status: dict | None = None) -> WatchlistSymbolMeta:
    symbol = str(ticker or "").upper().strip()
    known = {row.ticker: row for row in demo_symbols()}
    row = known.get(symbol)
    if row is not None:
        return WatchlistSymbolMeta(
            ticker=row.ticker,
            display_name=row.display_name,
            category=row.category,
        )

    status = status or {}
    return WatchlistSymbolMeta(
        ticker=symbol,
        display_name=str(status.get("display_name") or symbol),
        category=str(status.get("category") or "Other"),
    )


def group_watchlist_symbols(
    tickers: list[str],
    status_map: dict[str, dict],
) -> dict[str, list[WatchlistSymbolMeta]]:
    groups: dict[str, list[WatchlistSymbolMeta]] = {}
    for raw in tickers:
        meta = symbol_metadata(raw, status_map.get(str(raw).upper(), {}))
        groups.setdefault(meta.category, []).append(meta)

    ordered: dict[str, list[WatchlistSymbolMeta]] = {}
    for sector in SECTOR_ORDER:
        rows = groups.get(sector)
        if rows:
            ordered[sector] = rows
    for sector in sorted(set(groups) - set(ordered)):
        ordered[sector] = groups[sector]
    return ordered


def render_watchlist_market_card(
    *,
    meta: WatchlistSymbolMeta,
    status: dict,
    horizon_days: int,
    selected: bool,
    key_prefix: str,
) -> bool:
    available = bool(status.get("available")) or bool(status.get("forecasts"))
    forecast = forecast_for_horizon(status.get("forecasts") or [], horizon_days)

    expected = forecast.get("expected_return_pct") if forecast else None
    probability = forecast.get("probability_up_pct") if forecast else None
    projected = forecast.get("projected_price") if forecast else None
    current = status.get("current_price")

    prob_value = _number(probability)
    prob_width = 50 if prob_value is None else max(3, min(100, prob_value))
    move_class = _move_class(expected)
    status_text = _age_label(status.get("age_hours")) if available else "Forecast unavailable"
    status_class = "mf-ready" if forecast else "mf-wait"
    selected_class = " mf-market-card-selected" if selected else ""
    selected_tag = '<span class="mf-selected-tag">Selected</span>' if selected else ""
    icon = _CATEGORY_ICONS.get(meta.category, meta.ticker[:1] or "•")

    st.markdown(
        f"""
<div class="mf-market-card{selected_class}">
  <div class="mf-card-top">
    <div class="mf-symbol-lockup">
      <div class="mf-symbol-icon">{html.escape(icon)}</div>
      <div>
        <div class="mf-ticker">{html.escape(meta.ticker)}</div>
        <div class="mf-company">{html.escape(meta.display_name)}</div>
      </div>
    </div>
    <span class="mf-sector-chip">{html.escape(meta.category)}</span>
  </div>

  <div class="mf-price-row">
    <div>
      <div class="mf-price-label">Current price</div>
      <div class="mf-price">{html.escape(_fmt_money(current))}</div>
    </div>
    <span class="mf-move {move_class}">{html.escape(_fmt_pct(expected, signed=True))}</span>
  </div>

  <div class="mf-price-row" style="margin-top:.25rem">
    <div>
      <div class="mf-price-label">{horizon_days}D projected price</div>
      <div style="font-weight:800;font-size:1.05rem">{html.escape(_fmt_money(projected))}</div>
    </div>
    <div class="mf-price-label">{horizon_days}D forecast</div>
  </div>

  <div class="mf-prob-wrap">
    <div class="mf-prob-head">
      <span>Chance of finishing higher</span>
      <strong>{html.escape(_fmt_pct(probability))}</strong>
    </div>
    <div class="mf-prob-track">
      <div class="mf-prob-fill" style="width:{prob_width:.0f}%"></div>
    </div>
  </div>

  <div class="mf-card-footer">
    <span>{horizon_days}D projected move</span>
    <span class="{status_class}">{html.escape(status_text)}</span>
    {selected_tag}
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    return st.button(
        "Viewing forecast" if selected else f"Open {meta.ticker} forecast",
        key=f"{key_prefix}_open_{meta.ticker}",
        use_container_width=True,
        type="primary" if selected else "secondary",
        disabled=not forecast,
    )


def render_horizon_selector(*, key: str = "watchlist_horizon") -> int:
    options = ("1D", "5D", "10D", "20D")
    current = st.session_state.get(key)
    if current not in options:
        st.session_state[key] = "10D"

    choice = st.segmented_control(
        "Forecast horizon",
        options,
        key=key,
        label_visibility="collapsed",
    )
    label = str(choice or st.session_state.get(key) or "10D")
    try:
        return int(label.rstrip("D"))
    except Exception:
        return 10
