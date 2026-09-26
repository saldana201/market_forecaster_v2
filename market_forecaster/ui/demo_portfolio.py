"""Session-only Demo portfolio UI with cached market valuation."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from market_forecaster.core.demo_universe import is_demo_ticker
from market_forecaster.core.entitlements import check_position_limit, entitlements_for
from market_forecaster.core.session_identity import ensure_demo_session, resolve_identity
from market_forecaster.services.forecast_access import demo_cache_status
from market_forecaster.ui.design_system import (
    render_kpi_strip,
    render_page_header,
    render_section_header,
)
from market_forecaster.ui.market_cards import render_horizon_selector
from market_forecaster.ui.portfolio_cards import (
    build_portfolio_snapshot,
    render_portfolio_position_card,
    render_sector_allocation,
)


def _normalize_rows(frame: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for raw in frame.to_dict("records"):
        ticker = str(raw.get("ticker") or "").upper().strip()
        quantity = raw.get("quantity")
        cost_basis = raw.get("cost_basis")
        if not ticker:
            continue
        if not is_demo_ticker(ticker):
            raise ValueError(f"{ticker} is not available in the Demo portfolio.")
        if ticker in seen:
            raise ValueError(f"Duplicate Demo portfolio ticker: {ticker}")
        if pd.isna(quantity) or pd.isna(cost_basis):
            raise ValueError(f"Quantity and cost basis are required for {ticker}.")
        quantity = float(quantity)
        cost_basis = float(cost_basis)
        if quantity == 0:
            raise ValueError(f"Quantity for {ticker} must be non-zero.")
        if cost_basis <= 0:
            raise ValueError(f"Cost basis for {ticker} must be greater than zero.")
        seen.add(ticker)
        rows.append({"ticker": ticker, "quantity": quantity, "cost_basis": cost_basis})
    return rows


def _cost_basis_value(positions: list[dict]) -> float:
    total = 0.0
    for row in positions:
        try:
            total += abs(float(row["quantity"]) * float(row["cost_basis"]))
        except Exception:
            continue
    return total


def _portfolio_valuation(positions: list[dict], cache_map: dict[str, dict]) -> tuple[list[dict], float, float]:
    rows: list[dict] = []
    market_value_total = 0.0
    unrealized_total = 0.0
    for row in positions:
        ticker = row["ticker"]
        quantity = float(row["quantity"])
        cost_basis = float(row["cost_basis"])
        price = cache_map.get(ticker, {}).get("current_price")
        try:
            price = float(price)
        except Exception:
            price = None

        market_value = quantity * price if price is not None else None
        unrealized = (price - cost_basis) * quantity if price is not None else None
        unrealized_pct = (
            ((price / cost_basis) - 1.0) * 100.0 * (1 if quantity > 0 else -1)
            if price is not None and cost_basis > 0
            else None
        )
        if market_value is not None:
            market_value_total += market_value
        if unrealized is not None:
            unrealized_total += unrealized

        rows.append({
            **row,
            "current_price": price,
            "market_value": market_value,
            "unrealized": unrealized,
            "unrealized_pct": unrealized_pct,
        })
    return rows, market_value_total, unrealized_total


def _money(value) -> str:
    if value is None:
        return "—"
    return "$" + f"{float(value):,.2f}"


def render_demo_portfolio() -> None:
    session = ensure_demo_session(st.session_state)
    identity = resolve_identity(st.session_state)
    portfolio = session["portfolio"]
    rules = entitlements_for(identity)
    positions = portfolio.get("positions", [])
    cache_map = {row["ticker"]: row for row in demo_cache_status()}
    cash_value = float(portfolio.get("cash", 0.0) or 0.0)

    snapshot = build_portfolio_snapshot(
        positions,
        cash_value,
        cache_map,
        cost_key="cost_basis",
    )

    render_page_header(
        "Demo Portfolio",
        "Experiment with holdings, cost basis, allocation, open performance, and multi-horizon forecast outlook using cached market data.",
        eyebrow="Portfolio intelligence",
        badge="Demo · Session only",
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
                "caption": "Free Demo position capacity",
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
        active = str(st.session_state.get("ticker") or "").upper()
        for idx, row in enumerate(snapshot["positions"]):
            with cols[idx % 3]:
                opened = render_portfolio_position_card(
                    row,
                    horizon_days=horizon_days,
                    key_prefix="demo_portfolio",
                    selected=row["ticker"] == active,
                )
                if opened:
                    st.session_state["ticker"] = row["ticker"]
                    st.session_state["demo_selected_ticker"] = row["ticker"]
                    st.rerun()
    else:
        with st.container(border=True):
            st.markdown("### Build your Demo portfolio")
            st.caption(
                "Add a Demo ticker, quantity, and average cost below. The dashboard will calculate "
                "allocation, market value, open P/L, and multi-horizon forecast outlook."
            )

    render_section_header(
        "Manage Demo holdings",
        "Use symbols from Market Explorer. Nothing here is written to persistent account storage.",
    )
    with st.container(border=True):
        cash = st.number_input(
            "Cash / unallocated capital",
            min_value=0.0,
            step=100.0,
            value=cash_value,
            key="demo_portfolio_cash",
        )
        frame = pd.DataFrame(positions, columns=["ticker", "quantity", "cost_basis"])
        edited = st.data_editor(
            frame,
            num_rows="dynamic",
            use_container_width=True,
            key="demo_portfolio_editor",
            column_config={
                "ticker": st.column_config.TextColumn("Ticker"),
                "quantity": st.column_config.NumberColumn("Quantity", format="%.4f"),
                "cost_basis": st.column_config.NumberColumn(
                    "Average cost",
                    min_value=0.0,
                    format="$%.2f",
                ),
            },
        )
        if st.button(
            "Update Demo Portfolio",
            key="demo_portfolio_save",
            use_container_width=True,
            type="primary",
        ):
            try:
                rows = _normalize_rows(edited)
                if not check_position_limit(identity, len(rows)):
                    st.warning("Demo position limit reached.")
                    return
                portfolio["cash"] = float(cash)
                portfolio["positions"] = rows
                st.success("Demo portfolio updated for this session.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    st.markdown(
        """
<div class="mf-session-note">
<strong>Portfolio persistence is an account feature.</strong>
Standard keeps holdings and cost basis securely attached to your account across sessions and devices.
</div>
        """,
        unsafe_allow_html=True,
    )

