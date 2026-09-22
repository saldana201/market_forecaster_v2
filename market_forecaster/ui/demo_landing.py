"""Modern anonymous Demo landing experience for Market Forecaster 4.1.0."""
from __future__ import annotations

import html

import streamlit as st

from market_forecaster.core.demo_universe import demo_groups, demo_symbols
from market_forecaster.core.session_identity import ensure_demo_session
from market_forecaster.services.forecast_access import demo_cache_status
from market_forecaster.ui.demo_theme import inject_demo_theme

_FEATURED = ("SPY", "QQQ", "AAPL", "MSFT")
_CATEGORY_ICONS = {
    "Technology": "◈",
    "Financials": "◇",
    "Healthcare": "✚",
    "Energy": "◆",
    "Consumer": "●",
    "Industrials": "⬡",
    "Broad Market": "◎",
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


def _render_market_card(row, status: dict, current: str) -> bool:
    selected = row.ticker == current
    available = bool(status.get("available"))
    anchor = _anchor_forecast(status.get("forecasts") or [])
    expected = anchor.get("expected_return_pct") if anchor else None
    probability = anchor.get("probability_up_pct") if anchor else None
    horizon = int(anchor.get("horizon_days", 0) or 0) if anchor else 0
    outlook_label = f"{horizon}D outlook" if horizon else "Outlook"
    price = status.get("current_price")

    status_class = "mf-status-ready" if available else "mf-status-wait"
    status_text = _age_label(status.get("age_hours")) if available else "Preparing forecast"
    selected_text = " · Selected" if selected else ""
    icon = _CATEGORY_ICONS.get(row.category, "•")

    with st.container(border=True):
        st.markdown(
            f"""
<div>
  <div class="mf-section-kicker">{html.escape(icon)} {html.escape(row.category)}{selected_text}</div>
  <div class="mf-market-title">{html.escape(row.ticker)} · {html.escape(row.display_name)}</div>
  <div class="mf-market-sub">{html.escape(row.asset_type.upper())} · Full-quality shared Forecast Contract</div>
  <span class="mf-status {status_class}">{html.escape(status_text)}</span>
  <div class="mf-card-meta">
      <div><span>Current</span><strong>{html.escape(_fmt_money(price))}</strong></div>
      <div><span>{html.escape(outlook_label)}</span><strong>{html.escape(_fmt_pct(expected, signed=True))}</strong></div>
      <div><span>Chance up</span><strong>{html.escape(_fmt_pct(probability))}</strong></div>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )
        label = "Viewing forecast" if selected else f"View {row.ticker} forecast →"
        clicked = st.button(
            label,
            key=f"demo_symbol_{row.ticker}",
            use_container_width=True,
            type="primary" if selected else "secondary",
            disabled=not available,
        )
        if not available:
            st.caption("This symbol will appear automatically after its scheduled cache refresh.")
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
  <div><span class="mf-live-dot"></span>{ready_count}/{total_count} demo markets ready</div>
</div>
<div class="mf-hero">
  <span class="mf-eyebrow">Free Demo · No account required</span>
  <h1>See where the market may be headed—before you build your own watchlist.</h1>
  <p>
    Explore calibrated 1-day, 5-day, 10-day and 20-day forecasts across a curated market set.
    Demo forecasts use the same Forecast Contract quality as the paid platform; the difference
    is ticker access, persistence and research tooling.
  </p>
  <div class="mf-stat-strip">
    <div class="mf-stat"><strong>{total_count} markets</strong><span>Curated cross-sector universe</span></div>
    <div class="mf-stat"><strong>4 horizons</strong><span>1D · 5D · 10D · 20D</span></div>
    <div class="mf-stat"><strong>Shared cache</strong><span>No anonymous retraining</span></div>
    <div class="mf-stat"><strong>Session private</strong><span>Watchlist & portfolio stay temporary</span></div>
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
        placeholder="Search ticker or company name…",
        key="demo_market_search",
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
            if search in row.ticker.lower() or search in row.display_name.lower()
        ]

    st.markdown("### Market Explorer")
    st.caption("Select a market to open its latest cached forecast. Unavailable cards never trigger model training.")

    if not rows:
        st.info("No Demo markets match that filter.")
        return current

    columns = st.columns(2)
    for idx, row in enumerate(rows):
        with columns[idx % 2]:
            if _render_market_card(row, status_map.get(row.ticker, {}), current):
                current = row.ticker
                st.session_state["ticker"] = row.ticker
                st.session_state["demo_selected_ticker"] = row.ticker
                st.rerun()

    st.markdown(
        """
<div class="mf-session-note">
<strong>Want your own ticker?</strong> Standard will unlock custom supported symbols and permanent
watchlists/portfolios. Pro will add the Research Lab, model diagnostics and API access.
</div>
        """,
        unsafe_allow_html=True,
    )
    return current
