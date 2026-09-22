"""Session-only Demo watchlist UI."""
from __future__ import annotations

import streamlit as st

from market_forecaster.core.demo_universe import is_demo_ticker
from market_forecaster.core.entitlements import check_watchlist_limit, entitlements_for
from market_forecaster.core.session_identity import ensure_demo_session, resolve_identity


def render_demo_watchlist(active_ticker: str) -> None:
    session = ensure_demo_session(st.session_state)
    identity = resolve_identity(st.session_state)
    watchlist = session["watchlist"]
    rules = entitlements_for(identity)

    st.markdown("## My Demo Watchlist")
    st.caption("A lightweight workspace for this browser session. Nothing is permanently saved.")

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Tracked", len(watchlist))
    with m2:
        st.metric("Demo limit", rules.watchlist_limit)
    with m3:
        st.metric("Persistence", "Session only")

    ticker = str(active_ticker or "").upper().strip()
    if ticker and is_demo_ticker(ticker) and ticker not in watchlist:
        if st.button(
            f"+ Add {ticker} to watchlist",
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
            st.markdown("### Nothing here yet")
            st.caption("Open a forecast in Discover, then add it to your Demo Watchlist.")
        return

    st.markdown("### Saved this session")
    cols = st.columns(3)
    for idx, symbol in enumerate(list(watchlist)):
        with cols[idx % 3]:
            with st.container(border=True):
                st.markdown(f"### {symbol}")
                st.caption("Demo market")
                if st.button(
                    "Open forecast",
                    key=f"demo_watch_open_{symbol}",
                    use_container_width=True,
                ):
                    st.session_state["ticker"] = symbol
                    st.session_state["demo_selected_ticker"] = symbol
                    st.rerun()
                if st.button(
                    "Remove",
                    key=f"demo_watch_remove_{symbol}",
                    use_container_width=True,
                ):
                    watchlist.remove(symbol)
                    st.rerun()

    st.info(
        "Standard will make this watchlist persistent across sessions and devices. "
        "Your Demo list is intentionally not written to disk or a database."
    )
