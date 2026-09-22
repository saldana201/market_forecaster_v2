"""Session-only Demo watchlist UI with live cached forecast context."""
from __future__ import annotations

import streamlit as st

from market_forecaster.core.demo_universe import is_demo_ticker
from market_forecaster.core.entitlements import check_watchlist_limit, entitlements_for
from market_forecaster.core.session_identity import ensure_demo_session, resolve_identity
from market_forecaster.services.forecast_access import demo_cache_status


def _anchor(forecasts: list[dict]) -> dict:
    by_horizon = {int(row.get("horizon_days", -1)): row for row in forecasts or []}
    return by_horizon.get(10) or by_horizon.get(5) or by_horizon.get(20) or by_horizon.get(1) or {}


def _money(value) -> str:
    try:
        return "$" + f"{float(value):,.2f}"
    except Exception:
        return "—"


def _pct(value, signed: bool = False) -> str:
    try:
        number = float(value)
        return f"{number:+.1f}%" if signed else f"{number:.0f}%"
    except Exception:
        return "—"


def render_demo_watchlist(active_ticker: str) -> None:
    session = ensure_demo_session(st.session_state)
    identity = resolve_identity(st.session_state)
    watchlist = session["watchlist"]
    rules = entitlements_for(identity)
    cache_map = {row["ticker"]: row for row in demo_cache_status()}

    st.markdown("## My Market Watchlist")
    st.caption("A private session workspace for markets you want to revisit quickly.")

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Tracked markets", len(watchlist))
    with m2:
        st.metric("Free Demo capacity", f"{len(watchlist)} / {rules.watchlist_limit}")
    with m3:
        st.metric("Storage", "Session only")

    ticker = str(active_ticker or "").upper().strip()
    if ticker and is_demo_ticker(ticker) and ticker not in watchlist:
        if st.button(
            f"+ Add {ticker} to My Watchlist",
            key=f"demo_watch_add_{ticker}",
            use_container_width=True,
            type="primary",
        ):
            if not check_watchlist_limit(identity, len(watchlist) + 1):
                st.warning("Demo watchlist limit reached. Standard will provide a larger persistent watchlist.")
            else:
                watchlist.append(ticker)
                st.rerun()

    if not watchlist:
        with st.container(border=True):
            st.markdown("### Build your first watchlist")
            st.caption("Open a market from Discover and add it here. Your selections stay private to this session.")
        return

    st.markdown("### Markets you’re tracking")
    cols = st.columns(3)
    for idx, symbol in enumerate(list(watchlist)):
        status = cache_map.get(symbol, {})
        anchor = _anchor(status.get("forecasts") or [])
        expected = anchor.get("expected_return_pct")
        chance = anchor.get("probability_up_pct")
        horizon = int(anchor.get("horizon_days", 0) or 0)
        with cols[idx % 3]:
            with st.container(border=True):
                st.markdown(f"### {symbol}")
                st.caption(f"{horizon}D forecast snapshot" if horizon else "Cached forecast snapshot")
                c1, c2 = st.columns(2)
                with c1:
                    st.metric("Current", _money(status.get("current_price")))
                with c2:
                    st.metric("Projected move", _pct(expected, signed=True))
                st.progress(
                    max(0, min(100, int(float(chance)))) if chance is not None else 50,
                    text=f"Chance higher: {_pct(chance)}",
                )
                if st.button(
                    "Open forecast",
                    key=f"demo_watch_open_{symbol}",
                    use_container_width=True,
                    type="primary" if symbol == ticker else "secondary",
                ):
                    st.session_state["ticker"] = symbol
                    st.session_state["demo_selected_ticker"] = symbol
                    st.rerun()
                if st.button(
                    "Remove from watchlist",
                    key=f"demo_watch_remove_{symbol}",
                    use_container_width=True,
                ):
                    watchlist.remove(symbol)
                    st.rerun()

    st.markdown(
        """
<div class="mf-session-note">
<strong>Your Demo watchlist is intentionally temporary.</strong>
Standard will keep it synchronized across sessions and devices without changing forecast quality.
</div>
        """,
        unsafe_allow_html=True,
    )
