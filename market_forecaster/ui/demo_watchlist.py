"""Session-only Demo watchlist with sector-grouped multi-horizon forecast cards."""
from __future__ import annotations

import streamlit as st

from market_forecaster.core.demo_universe import is_demo_ticker
from market_forecaster.core.entitlements import check_watchlist_limit, entitlements_for
from market_forecaster.core.session_identity import ensure_demo_session, resolve_identity
from market_forecaster.services.forecast_access import demo_cache_status
from market_forecaster.ui.design_system import (
    render_kpi_strip,
    render_page_header,
    render_section_header,
)
from market_forecaster.ui.market_cards import (
    group_watchlist_symbols,
    render_horizon_selector,
    render_watchlist_market_card,
)


def render_demo_watchlist(active_ticker: str) -> None:
    session = ensure_demo_session(st.session_state)
    identity = resolve_identity(st.session_state)
    watchlist = session["watchlist"]
    rules = entitlements_for(identity)
    cache_map = {row["ticker"]: row for row in demo_cache_status()}

    render_page_header(
        "My Market Watchlist",
        "Track markets by sector and compare the same 1D, 5D, 10D, and 20D Forecast Contracts used in Market Explorer.",
        eyebrow="Market workspace",
        badge="Demo · Session only",
    )
    render_kpi_strip(
        [
            {
                "label": "Tracked markets",
                "value": str(len(watchlist)),
                "caption": "Markets currently in this session",
                "tone": "accent",
            },
            {
                "label": "Plan capacity",
                "value": f"{len(watchlist)} / {rules.watchlist_limit}",
                "caption": "Free Demo watchlist limit",
            },
            {
                "label": "Storage",
                "value": "Session",
                "caption": "Clears when the Demo session expires",
            },
        ]
    )

    ticker = str(active_ticker or "").upper().strip()
    if ticker and is_demo_ticker(ticker) and ticker not in watchlist:
        if st.button(
            f"+ Add {ticker} to My Watchlist",
            key=f"demo_watch_add_{ticker}",
            use_container_width=True,
            type="primary",
        ):
            if not check_watchlist_limit(identity, len(watchlist) + 1):
                st.warning(
                    "Demo watchlist limit reached. Standard will provide a larger persistent watchlist."
                )
            else:
                watchlist.append(ticker)
                st.rerun()

    if not watchlist:
        with st.container(border=True):
            st.markdown("### Build your first watchlist")
            st.caption(
                "Open a market from Discover and add it here. Your selections stay private to this session."
            )
        return

    selector_left, selector_right = st.columns([2, 5])
    with selector_left:
        st.markdown("### Forecast horizon")
        horizon_days = render_horizon_selector(key="watchlist_horizon")
    with selector_right:
        st.caption(
            "Switch the horizon once to update every ticker card below. Cards remain grouped by market sector."
        )

    groups = group_watchlist_symbols(list(watchlist), cache_map)

    for sector, rows in groups.items():
        render_section_header(
            sector,
            f"{len(rows)} tracked market{'s' if len(rows) != 1 else ''}",
        )

        cols = st.columns(3)
        for idx, meta in enumerate(rows):
            status = cache_map.get(meta.ticker, {})
            with cols[idx % 3]:
                opened = render_watchlist_market_card(
                    meta=meta,
                    status=status,
                    horizon_days=horizon_days,
                    selected=meta.ticker == ticker,
                    key_prefix="demo_watch",
                )
                if opened:
                    st.session_state["ticker"] = meta.ticker
                    st.session_state["demo_selected_ticker"] = meta.ticker
                    st.rerun()

                if st.button(
                    "Remove from watchlist",
                    key=f"demo_watch_remove_{meta.ticker}",
                    use_container_width=True,
                ):
                    watchlist.remove(meta.ticker)
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
