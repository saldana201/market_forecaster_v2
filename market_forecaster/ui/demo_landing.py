"""Premium anonymous Demo landing experience for Market Forecaster 4.1.1."""
from __future__ import annotations

import html

import streamlit as st

from market_forecaster.core.demo_universe import demo_groups, demo_symbols
from market_forecaster.core.session_identity import ensure_demo_session
from market_forecaster.services.forecast_access import demo_cache_status
from market_forecaster.ui.demo_theme import inject_demo_theme

_FEATURED = ("SPY", "QQQ", "AAPL", "MSFT", "JPM", "LLY")
_CATEGORY_ICONS = {
    "Technology": "T",
    "Financials": "$",
    "Healthcare": "+",
    "Energy": "E",
    "Consumer": "C",
    "Industrials": "I",
    "Broad Market": "M",
}


def _number(value):
    try:
        return float(value)
    except Exception:
        return None


def _anchor_forecast(forecasts: list[dict]) -> dict | None:
    by_horizon = {int(row.get("horizon_days", -1)): row for row in forecasts or []}
    for horizon in (10, 5, 20, 1):
        if horizon in by_horizon:
            return by_horizon[horizon]
    return next(iter(forecasts or []), None)


def _fmt_money(value) -> str:
    value = _number(value)
    return "—" if value is None else "$" + f"{value:,.2f}"


def _fmt_pct(value, *, signed: bool = False) -> str:
    value = _number(value)
    if value is None:
        return "—"
    return f"{value:+.1f}%" if signed else f"{value:.0f}%"


def _age_label(age_hours) -> str:
    value = _number(age_hours)
    if value is None:
        return "Cached"
    if value < 1:
        return "Updated <1h ago"
    if value < 24:
        return f"Updated {int(value)}h ago"
    return f"Updated {int(value // 24)}d ago"


def _move_class(expected) -> str:
    value = _number(expected)
    if value is None or abs(value) < 0.05:
        return "mf-move-flat"
    return "mf-move-up" if value > 0 else "mf-move-down"


def _symbol_initial(row) -> str:
    if row.category == "Broad Market":
        return "M"
    return _CATEGORY_ICONS.get(row.category, row.ticker[:1])


def _render_market_card(row, status: dict, current: str) -> bool:
    selected = row.ticker == current
    available = bool(status.get("available"))
    anchor = _anchor_forecast(status.get("forecasts") or [])
    expected = anchor.get("expected_return_pct") if anchor else None
    probability = anchor.get("probability_up_pct") if anchor else None
    horizon = int(anchor.get("horizon_days", 0) or 0) if anchor else 0
    price = status.get("current_price")

    prob_value = _number(probability)
    prob_width = 50 if prob_value is None else max(3, min(100, prob_value))
    status_text = _age_label(status.get("age_hours")) if available else "Forecast preparing"
    status_class = "mf-ready" if available else "mf-wait"
    selected_class = " mf-market-card-selected" if selected else ""
    selected_tag = '<span class="mf-selected-tag">Selected</span>' if selected else ""
    move_class = _move_class(expected)
    horizon_label = f"{horizon}D projected move" if horizon else "Projected move"

    st.markdown(
        f"""
<div class="mf-market-card{selected_class}">
  <div class="mf-card-top">
    <div class="mf-symbol-lockup">
      <div class="mf-symbol-icon">{html.escape(_symbol_initial(row))}</div>
      <div>
        <div class="mf-ticker">{html.escape(row.ticker)}</div>
        <div class="mf-company">{html.escape(row.display_name)}</div>
      </div>
    </div>
    <span class="mf-sector-chip">{html.escape(row.category)}</span>
  </div>

  <div class="mf-price-row">
    <div>
      <div class="mf-price-label">Current price</div>
      <div class="mf-price">{html.escape(_fmt_money(price))}</div>
    </div>
    <span class="mf-move {move_class}">{html.escape(_fmt_pct(expected, signed=True))}</span>
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
    <span>{html.escape(horizon_label)}</span>
    <span class="{status_class}">{html.escape(status_text)}</span>
    {selected_tag}
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    label = "Viewing forecast" if selected else f"Open {row.ticker} forecast"
    clicked = st.button(
        label,
        key=f"demo_symbol_{row.ticker}",
        use_container_width=True,
        type="primary" if selected else "secondary",
        disabled=not available,
    )
    if not available:
        st.caption("Will activate automatically after the next scheduled refresh.")
    return clicked


def render_demo_landing(current_ticker: str | None = None) -> str:
    inject_demo_theme()
    ensure_demo_session(st.session_state)
    current = str(current_ticker or st.session_state.get("ticker") or "SPY").upper().strip()

    statuses = demo_cache_status()
    status_map = {row["ticker"]: row for row in statuses}
    ready_count = sum(1 for row in statuses if row.get("available"))
    total_count = len(statuses)

    st.markdown(
        f"""
<div class="mf-brandbar">
  <div><span class="mf-brand">OneEight AI Systems</span> / Market Forecaster</div>
  <div><span class="mf-live-dot"></span>{ready_count}/{total_count} markets live</div>
</div>
<div class="mf-hero">
  <span class="mf-eyebrow">Free Market Forecast Demo</span>
  <h1>Professional market forecasts without the clutter.</h1>
  <p>
    Explore the same governed Forecast Contract used by the platform across a curated set of major markets.
    Compare projected price, expected move, probability, and uncertainty before creating an account.
  </p>
  <div class="mf-stat-strip">
    <div class="mf-stat"><strong>{total_count} curated markets</strong><span>Technology, financials, healthcare, energy and more</span></div>
    <div class="mf-stat"><strong>4 forecast horizons</strong><span>1D · 5D · 10D · 20D</span></div>
    <div class="mf-stat"><strong>Full forecast quality</strong><span>Demo is not a lower-quality model</span></div>
    <div class="mf-stat"><strong>Private session tools</strong><span>Temporary watchlist and portfolio</span></div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    groups = demo_groups()
    categories = ["Featured", "All"] + list(groups.keys())
    selected_category = st.radio(
        "Market category",
        categories,
        horizontal=True,
        label_visibility="collapsed",
        key="demo_market_category",
    )

    search = st.text_input(
        "Search the Demo universe",
        placeholder="Search AAPL, JPM, Microsoft, healthcare…",
        key="demo_market_search",
        label_visibility="collapsed",
    ).strip().lower()

    if selected_category == "Featured":
        rows = [row for row in demo_symbols() if row.ticker in _FEATURED]
        rows.sort(key=lambda row: _FEATURED.index(row.ticker))
    elif selected_category == "All":
        rows = demo_symbols()
    else:
        rows = groups.get(selected_category, [])

    if search:
        rows = [
            row for row in rows
            if search in row.ticker.lower()
            or search in row.display_name.lower()
            or search in row.category.lower()
        ]

    st.markdown(
        """
<div class="mf-section-head">
  <div>
    <div class="mf-section-title">Market Explorer</div>
    <div class="mf-section-copy">Choose a market and open its latest shared forecast.</div>
  </div>
  <div class="mf-section-copy">Anonymous traffic never triggers model training.</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    if not rows:
        st.info("No Demo markets match that filter.")
        return current

    columns = st.columns(3)
    for idx, row in enumerate(rows):
        with columns[idx % 3]:
            if _render_market_card(row, status_map.get(row.ticker, {}), current):
                current = row.ticker
                st.session_state["ticker"] = row.ticker
                st.session_state["demo_selected_ticker"] = row.ticker
                st.rerun()

    st.markdown(
        """
<div class="mf-session-note">
<strong>Ready for your own symbols?</strong>
Standard will unlock custom supported tickers plus persistent watchlists and portfolios.
Pro will add Research Lab diagnostics, model research and API access.
</div>
        """,
        unsafe_allow_html=True,
    )
    return current
