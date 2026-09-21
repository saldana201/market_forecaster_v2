"""Session-only Demo watchlist UI."""
from __future__ import annotations

import streamlit as st

from market_forecaster.core.demo_universe import is_demo_ticker
from market_forecaster.core.entitlements import check_watchlist_limit
from market_forecaster.core.session_identity import ensure_demo_session, resolve_identity


def render_demo_watchlist(active_ticker: str) -> None:
    session = ensure_demo_session(st.session_state)
    identity = resolve_identity(st.session_state)
    watchlist = session["watchlist"]

    st.markdown("#### Demo Watchlist")
    st.caption("Saved for this session only.")

    ticker = str(active_ticker or "").upper().strip()
    if ticker and is_demo_ticker(ticker) and ticker not in watchlist:
        if st.button(f"Add {ticker} to Demo Watchlist", key=f"demo_watch_add_{ticker}", use_container_width=True):
            if not check_watchlist_limit(identity, len(watchlist) + 1):
                st.warning("Demo watchlist limit reached. Upgrade plans will provide larger persistent watchlists.")
            else:
                watchlist.append(ticker)
                st.rerun()

    if not watchlist:
        st.caption("No symbols added yet.")
        return

    for symbol in list(watchlist):
        c1, c2 = st.columns([4, 1])
        with c1:
            st.write(symbol)
        with c2:
            if st.button("Remove", key=f"demo_watch_remove_{symbol}"):
                watchlist.remove(symbol)
                st.rerun()
