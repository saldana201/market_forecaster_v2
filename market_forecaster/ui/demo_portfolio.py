"""Session-only Demo portfolio UI with cached market valuation."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from market_forecaster.core.demo_universe import is_demo_ticker
from market_forecaster.core.entitlements import check_position_limit, entitlements_for
from market_forecaster.core.session_identity import ensure_demo_session, resolve_identity
from market_forecaster.services.forecast_access import demo_cache_status


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
    valued, market_value, unrealized = _portfolio_valuation(positions, cache_map)

    st.markdown("## Demo Portfolio")
    st.caption(
        "Experiment with holdings and cost basis using cached market prices. "
        "Everything here remains private to the current session."
    )

    cash_value = float(portfolio.get("cash", 0.0) or 0.0)
    net_value = cash_value + market_value

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Portfolio value", _money(net_value))
    with m2:
        st.metric("Cash", _money(cash_value))
    with m3:
        st.metric("Unrealized P/L", _money(unrealized))
    with m4:
        st.metric("Positions", f"{len(positions)} / {rules.positions_per_portfolio}")

    if valued:
        st.markdown("### Position snapshot")
        cols = st.columns(3)
        for idx, row in enumerate(valued):
            with cols[idx % 3]:
                with st.container(border=True):
                    st.markdown(f"### {row['ticker']}")
                    st.caption("LONG" if row["quantity"] > 0 else "SHORT")
                    c1, c2 = st.columns(2)
                    with c1:
                        st.metric("Current", _money(row["current_price"]))
                    with c2:
                        st.metric(
                            "P/L",
                            _money(row["unrealized"]),
                            delta=None if row["unrealized_pct"] is None else f"{row['unrealized_pct']:+.1f}%",
                        )
                    st.caption(
                        f"{abs(row['quantity']):,.4f} shares · Avg. cost {_money(row['cost_basis'])}"
                    )
                    st.caption(f"Market value: {_money(row['market_value'])}")

    with st.container(border=True):
        st.markdown("### Edit Demo portfolio")
        st.caption("Use symbols from the Demo Market Explorer. No data is written to the legacy local portfolio file.")

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
                "cost_basis": st.column_config.NumberColumn("Average cost", min_value=0.0, format="$%.2f"),
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
Standard will keep holdings and cost basis securely attached to your account across sessions and devices.
</div>
        """,
        unsafe_allow_html=True,
    )
