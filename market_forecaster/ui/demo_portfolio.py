"""Session-only Demo portfolio UI."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from market_forecaster.core.demo_universe import is_demo_ticker
from market_forecaster.core.entitlements import check_position_limit
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


def render_demo_portfolio() -> None:
    session = ensure_demo_session(st.session_state)
    identity = resolve_identity(st.session_state)
    portfolio = session["portfolio"]

    st.markdown("#### Demo Portfolio")
    st.caption("Saved for this session only. Nothing is written to local portfolio files or a database.")

    cash = st.number_input(
        "Demo cash",
        min_value=0.0,
        step=100.0,
        value=float(portfolio.get("cash", 0.0) or 0.0),
        key="demo_portfolio_cash",
    )
    frame = pd.DataFrame(portfolio.get("positions", []), columns=["ticker", "quantity", "cost_basis"])
    edited = st.data_editor(
        frame,
        num_rows="dynamic",
        use_container_width=True,
        key="demo_portfolio_editor",
    )
    if st.button("Update Demo Portfolio", key="demo_portfolio_save", use_container_width=True):
        try:
            rows = _normalize_rows(edited)
            if not check_position_limit(identity, len(rows)):
                st.warning("Demo position limit reached.")
                return
            portfolio["cash"] = float(cash)
            portfolio["positions"] = rows
            st.success("Demo portfolio updated for this session.")
        except Exception as exc:
            st.error(str(exc))
