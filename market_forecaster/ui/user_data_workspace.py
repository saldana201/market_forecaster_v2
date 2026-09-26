"""Authenticated persistent Watchlist and Portfolio UI for Market Forecaster 4.1.2."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from market_forecaster.core.entitlements import (
    can_save_portfolio,
    can_save_watchlist,
    check_position_limit,
    check_watchlist_limit,
    entitlements_for,
)
from market_forecaster.core.session_identity import resolve_identity
from market_forecaster.persistence.supabase_data import PersistenceError
from market_forecaster.services.forecast_access import (
    ForecastAccessError,
    demo_cache_status,
    get_forecast_for_identity,
)
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
from market_forecaster.ui.portfolio_cards import (
    build_portfolio_snapshot,
    render_portfolio_position_card,
    render_sector_allocation,
)


def _money(value) -> str:
    try:
        return "$" + f"{float(value):,.2f}"
    except Exception:
        return "—"


def _contract_status_for_symbol(identity, symbol: str, demo_map: dict[str, dict]) -> dict:
    symbol = str(symbol or "").upper().strip()
    if symbol in demo_map:
        return demo_map[symbol]

    try:
        result = get_forecast_for_identity(identity, symbol)
        contract = result.contract
    except ForecastAccessError:
        return {
            "ticker": symbol,
            "display_name": symbol,
            "category": "Other",
            "available": False,
            "source": "unavailable",
            "current_price": None,
            "forecasts": [],
            "age_hours": None,
        }

    generated_at = contract.get("generated_at")
    age_hours = None
    if generated_at:
        try:
            stamp = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            age_hours = max(
                0.0,
                (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds() / 3600.0,
            )
        except Exception:
            age_hours = None

    return {
        "ticker": symbol,
        "display_name": symbol,
        "category": "Other",
        "available": True,
        "source": result.source,
        "generated_at": generated_at,
        "current_price": contract.get("current_price"),
        "forecasts": contract.get("forecasts", []),
        "age_hours": age_hours,
    }


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
    render_page_header(
        "My Watchlist",
        "Saved to your account, grouped by sector, and rendered with the same forecast cards used in Market Explorer.",
        eyebrow="Market workspace",
        badge=f"{identity.plan.title()} · Persistent",
    )
    if not can_save_watchlist(identity):
        st.info("Persistent watchlists require an active Standard or Pro subscription.")
        return
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
    render_kpi_strip(
        [
            {
                "label": "Tracked markets",
                "value": str(len(symbols)),
                "caption": "Saved to this account",
                "tone": "accent",
            },
            {
                "label": "Plan capacity",
                "value": f"{len(symbols)} / {rules.watchlist_limit}",
                "caption": f"{identity.plan.title()} watchlist allowance",
            },
            {
                "label": "Storage",
                "value": "Account",
                "caption": "Persistent across sessions and devices",
            },
        ]
    )

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
            st.caption(
                "Open any market and add it here. It will follow your account across sessions."
            )
        return

    demo_map = {row["ticker"]: row for row in demo_cache_status()}
    status_map = {
        symbol: _contract_status_for_symbol(identity, symbol, demo_map)
        for symbol in symbols
    }

    selector_left, selector_right = st.columns([2, 5])
    with selector_left:
        st.markdown("### Forecast horizon")
        horizon_days = render_horizon_selector(key="watchlist_horizon")
    with selector_right:
        st.caption(
            "Choose 1D, 5D, 10D, or 20D once to update every tracked market below."
        )

    groups = group_watchlist_symbols(symbols, status_map)
    item_by_symbol = {
        str(row.get("ticker") or "").upper(): row
        for row in items
    }

    for sector, rows in groups.items():
        render_section_header(
            sector,
            f"{len(rows)} tracked market{'s' if len(rows) != 1 else ''}",
        )

        cols = st.columns(3)
        for idx, meta in enumerate(rows):
            status = status_map.get(meta.ticker, {})
            item = item_by_symbol.get(meta.ticker, {})
            with cols[idx % 3]:
                opened = render_watchlist_market_card(
                    meta=meta,
                    status=status,
                    horizon_days=horizon_days,
                    selected=meta.ticker == ticker,
                    key_prefix="persistent_watch",
                )
                if opened:
                    st.session_state["ticker"] = meta.ticker
                    st.rerun()

                if not status.get("available"):
                    st.caption(
                        "The ticker is saved, but no cached Forecast Contract is available yet."
                    )

                if st.button(
                    "Remove from watchlist",
                    key=f"persistent_watch_remove_{item.get('id', meta.ticker)}",
                    use_container_width=True,
                ):
                    try:
                        remove_watchlist_item(
                            client,
                            identity,
                            str(watchlist["id"]),
                            meta.ticker,
                        )
                        st.rerun()
                    except PersistenceError as exc:
                        st.error(f"Could not remove {meta.ticker}: {exc}")


def render_persistent_portfolio() -> None:
    client, identity = _persistent_client()
    render_page_header(
        "My Portfolio",
        "A live account view of holdings, cost basis, allocation, unrealized performance, and forward forecast outlook.",
        eyebrow="Portfolio intelligence",
        badge=f"{identity.plan.title()} · Persistent",
    )
    if not can_save_portfolio(identity):
        st.info("Persistent portfolios require an active Standard or Pro subscription.")
        return
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
    demo_map = {row["ticker"]: row for row in demo_cache_status()}
    symbols = [str(row.get("ticker") or "").upper() for row in positions]
    status_map = {
        symbol: _contract_status_for_symbol(identity, symbol, demo_map)
        for symbol in symbols
    }
    snapshot = build_portfolio_snapshot(
        positions,
        cash,
        status_map,
        cost_key="avg_cost",
    )

    pnl_tone = "positive" if snapshot["unrealized"] > 0 else (
        "negative" if snapshot["unrealized"] < 0 else "neutral"
    )
    return_tone = "positive" if snapshot["return_pct"] > 0 else (
        "negative" if snapshot["return_pct"] < 0 else "neutral"
    )
    render_kpi_strip(
        [
            {
                "label": "Portfolio value",
                "value": _money(snapshot["portfolio_value"]),
                "caption": "Cash + marked holdings",
                "tone": "accent",
            },
            {
                "label": "Invested capital",
                "value": _money(snapshot["invested_capital"]),
                "caption": "Absolute cost basis in open positions",
            },
            {
                "label": "Unrealized P/L",
                "value": _money(snapshot["unrealized"]),
                "caption": "Open-position profit / loss",
                "tone": pnl_tone,
            },
            {
                "label": "Open return",
                "value": f"{snapshot['return_pct']:+.1f}%",
                "caption": "Unrealized P/L ÷ invested capital",
                "tone": return_tone,
            },
            {
                "label": "Cash",
                "value": _money(snapshot["cash"]),
                "caption": f"{snapshot['cash_pct']:.1f}% of portfolio value",
            },
            {
                "label": "Positions",
                "value": f"{len(positions)} / {rules.positions_per_portfolio}",
                "caption": f"{identity.plan.title()} position capacity",
            },
        ]
    )

    if positions:
        allocation_col, outlook_col = st.columns([2, 3])
        with allocation_col:
            render_section_header(
                "Sector allocation",
                "Current gross market exposure by sector.",
            )
            render_sector_allocation(snapshot)
        with outlook_col:
            render_section_header(
                "Forecast horizon",
                "Use one horizon across every position card.",
            )
            horizon_days = render_horizon_selector(key="portfolio_horizon")

        render_section_header(
            "Position outlook",
            "Market value, open P/L, allocation, and forward Forecast Contract signals.",
            badge=f"{horizon_days}D",
        )
        cols = st.columns(3)
        for idx, row in enumerate(snapshot["positions"]):
            with cols[idx % 3]:
                opened = render_portfolio_position_card(
                    row,
                    horizon_days=horizon_days,
                    key_prefix="persistent_portfolio",
                    selected=row["ticker"] == str(st.session_state.get("ticker") or "").upper(),
                )
                if opened:
                    st.session_state["ticker"] = row["ticker"]
                    st.rerun()
    else:
        horizon_days = 10
        with st.container(border=True):
            st.markdown("### Build your portfolio")
            st.caption(
                "Add a ticker, quantity, and average cost below. Once saved, Portfolio will calculate "
                "allocation, market value, open P/L, and multi-horizon forecast outlook."
            )

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

    render_section_header(
        "Manage holdings",
        "Update cash, quantities, or average cost. Saving recalculates the portfolio dashboard.",
    )
    with st.container(border=True):
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

