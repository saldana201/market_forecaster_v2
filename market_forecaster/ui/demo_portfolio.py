"""Session-only Demo portfolio UI."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from market_forecaster.core.demo_universe import is_demo_ticker
from market_forecaster.core.entitlements import check_position_limit, entitlements_for
from market_forecaster.core.session_identity import ensure_demo_session, resolve_identity


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


def render_demo_portfolio() -> None:
    session = ensure_demo_session(st.session_state)
    identity = resolve_identity(st.session_state)
    portfolio = session["portfolio"]
    rules = entitlements_for(identity)
    positions = portfolio.get("positions", [])

    st.markdown("## Demo Portfolio")
    st.caption(
        "Experiment with holdings and cost basis without creating an account. "
        "This state exists only in the current Streamlit session."
    )

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Cash", "$" + f"{float(portfolio.get('cash', 0.0) or 0.0):,.0f}")
    with m2:
        st.metric("Positions", len(positions))
    with m3:
        st.metric("Cost basis value", "$" + f"{_cost_basis_value(positions):,.0f}")
    with m4:
        st.metric("Demo limit", rules.positions_per_portfolio)

    with st.container(border=True):
        st.markdown("### Edit portfolio")
        st.caption("Use only symbols available in the Demo Market Explorer.")

        cash = st.number_input(
            "Cash / unallocated capital",
            min_value=0.0,
            step=100.0,
            value=float(portfolio.get("cash", 0.0) or 0.0),
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
                "cost_basis": st.column_config.NumberColumn("Avg. cost", min_value=0.0, format="$%.2f"),
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

    st.info(
        "Standard will store portfolios securely to your account. "
        "Demo portfolio data is never written to the legacy local portfolio file."
    )
