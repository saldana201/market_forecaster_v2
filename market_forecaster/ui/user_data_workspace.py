"""Authenticated persistent Watchlist and Portfolio UI for Market Forecaster 4.1.2."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from market_forecaster.core.entitlements import (
    check_position_limit,
    check_watchlist_limit,
    entitlements_for,
)
from market_forecaster.core.session_identity import resolve_identity
from market_forecaster.persistence.supabase_data import PersistenceError
from market_forecaster.services.forecast_access import demo_cache_status
from market_forecaster.services.user_data import (
    add_watchlist_item,
    client_for_state,
    get_or_create_portfolio,
    get_or_create_watchlist,
    list_watchlist_items,
    load_portfolio_positions,
    persistence_configuration_status,
    remove_watchlist_item,
    save_primary_portfolio,
)


def _money(value) -> str:
    try:
        return "$" + f"{float(value):,.2f}"
    except Exception:
        return "—"


def _persistent_client():
    identity = resolve_identity(st.session_state)
    ready, reason = persistence_configuration_status()
    if not ready:
        st.info(
            "Persistent account storage is installed but not enabled for this deployment. "
            f"{reason}"
        )
        return None, identity
    try:
        return client_for_state(st.session_state, identity), identity
    except PersistenceError as exc:
        st.error(str(exc))
        return None, identity


def render_persistent_watchlist(active_ticker: str) -> None:
    client, identity = _persistent_client()
    st.markdown("## My Watchlist")
    st.caption("Saved to your account and protected by Supabase Row Level Security.")
    if client is None:
        return

    try:
        watchlist = get_or_create_watchlist(client, identity)
        items = list_watchlist_items(client, identity, str(watchlist["id"]))
    except PersistenceError as exc:
        st.error(f"Could not load watchlist: {exc}")
        return

    rules = entitlements_for(identity)
    symbols = [str(row.get("ticker") or "").upper() for row in items]
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Tracked markets", len(symbols))
    with c2:
        st.metric("Plan capacity", f"{len(symbols)} / {rules.watchlist_limit}")
    with c3:
        st.metric("Storage", "Account")

    ticker = str(active_ticker or "").upper().strip()
    if ticker and ticker not in symbols:
        if st.button(
            f"+ Add {ticker} to My Watchlist",
            key=f"persistent_watch_add_{ticker}",
            type="primary",
            use_container_width=True,
        ):
            if not check_watchlist_limit(identity, len(symbols) + 1):
                st.warning("Your plan watchlist limit has been reached.")
            else:
                try:
                    add_watchlist_item(
                        client,
                        identity,
                        str(watchlist["id"]),
                        ticker,
                        sort_order=len(symbols),
                    )
                    st.rerun()
                except PersistenceError as exc:
                    st.error(f"Could not save {ticker}: {exc}")

    if not items:
        with st.container(border=True):
            st.markdown("### Your watchlist is ready")
            st.caption("Open any market and add it here. It will follow your account across sessions.")
        return

    cache_map = {row["ticker"]: row for row in demo_cache_status()}
    cols = st.columns(3)
    for idx, row in enumerate(items):
        symbol = str(row.get("ticker") or "").upper()
        cache = cache_map.get(symbol, {})
        with cols[idx % 3]:
            with st.container(border=True):
                st.markdown(f"### {symbol}")
                st.metric("Current", _money(cache.get("current_price")))
                if not cache:
                    st.caption("Live cached Demo quote not available; the saved ticker is still persistent.")
                if st.button(
                    "Open forecast",
                    key=f"persistent_watch_open_{row['id']}",
                    use_container_width=True,
                    type="primary" if symbol == ticker else "secondary",
                ):
                    st.session_state["ticker"] = symbol
                    st.rerun()
                if st.button(
                    "Remove",
                    key=f"persistent_watch_remove_{row['id']}",
                    use_container_width=True,
                ):
                    try:
                        remove_watchlist_item(client, identity, str(watchlist["id"]), symbol)
                        st.rerun()
                    except PersistenceError as exc:
                        st.error(f"Could not remove {symbol}: {exc}")


def render_persistent_portfolio() -> None:
    client, identity = _persistent_client()
    st.markdown("## My Portfolio")
    st.caption("Holdings and cost basis are saved to your authenticated account.")
    if client is None:
        return

    try:
        portfolio = get_or_create_portfolio(client, identity)
        positions = load_portfolio_positions(client, identity, str(portfolio["id"]))
    except PersistenceError as exc:
        st.error(f"Could not load portfolio: {exc}")
        return

    cash = float(portfolio.get("cash") or 0.0)
    rules = entitlements_for(identity)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Cash", _money(cash))
    with c2:
        st.metric("Positions", f"{len(positions)} / {rules.positions_per_portfolio}")
    with c3:
        st.metric("Storage", "Account")

    frame = pd.DataFrame(
        [
            {
                "ticker": str(row.get("ticker") or "").upper(),
                "quantity": float(row.get("quantity") or 0),
                "avg_cost": float(row.get("avg_cost") or 0),
            }
            for row in positions
        ],
        columns=["ticker", "quantity", "avg_cost"],
    )

    with st.container(border=True):
        st.markdown("### Edit portfolio")
        cash_value = st.number_input(
            "Cash / unallocated capital",
            min_value=0.0,
            step=100.0,
            value=cash,
            key="persistent_portfolio_cash",
        )
        edited = st.data_editor(
            frame,
            num_rows="dynamic",
            use_container_width=True,
            key="persistent_portfolio_editor",
            column_config={
                "ticker": st.column_config.TextColumn("Ticker"),
                "quantity": st.column_config.NumberColumn("Quantity", min_value=0.0, format="%.4f"),
                "avg_cost": st.column_config.NumberColumn("Average cost", min_value=0.0, format="$%.2f"),
            },
        )

        if st.button(
            "Save Portfolio",
            key="persistent_portfolio_save",
            use_container_width=True,
            type="primary",
        ):
            normalized = []
            seen: set[str] = set()
            try:
                for raw in edited.to_dict("records"):
                    ticker = str(raw.get("ticker") or "").upper().strip()
                    if not ticker:
                        continue
                    if ticker in seen:
                        raise ValueError(f"Duplicate ticker: {ticker}")
                    quantity = float(raw.get("quantity") or 0)
                    avg_cost = float(raw.get("avg_cost") or 0)
                    if quantity <= 0:
                        raise ValueError(f"Quantity for {ticker} must be greater than zero.")
                    if avg_cost < 0:
                        raise ValueError(f"Average cost for {ticker} cannot be negative.")
                    seen.add(ticker)
                    normalized.append(
                        {"ticker": ticker, "quantity": quantity, "avg_cost": avg_cost}
                    )

                if not check_position_limit(identity, len(normalized)):
                    st.warning("Your plan position limit has been reached.")
                    return

                save_primary_portfolio(
                    client,
                    identity,
                    cash=float(cash_value),
                    positions=normalized,
                )
                st.success("Portfolio saved.")
                st.rerun()
            except (PersistenceError, ValueError) as exc:
                st.error(str(exc))
