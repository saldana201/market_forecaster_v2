"""Curated anonymous Demo universe for Market Forecaster 4.1.0."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoSymbol:
    ticker: str
    display_name: str
    category: str
    asset_type: str = "equity"
    display_order: int = 0
    enabled: bool = True
    refresh_policy: str = "after_market_close"


_DEMO_SYMBOLS = (
    DemoSymbol("AAPL", "Apple", "Technology", display_order=10),
    DemoSymbol("MSFT", "Microsoft", "Technology", display_order=20),
    DemoSymbol("JPM", "JPMorgan Chase", "Financials", display_order=30),
    DemoSymbol("BAC", "Bank of America", "Financials", display_order=40),
    DemoSymbol("LLY", "Eli Lilly", "Healthcare", display_order=50),
    DemoSymbol("JNJ", "Johnson & Johnson", "Healthcare", display_order=60),
    DemoSymbol("XOM", "Exxon Mobil", "Energy", display_order=70),
    DemoSymbol("CVX", "Chevron", "Energy", display_order=80),
    DemoSymbol("WMT", "Walmart", "Consumer", display_order=90),
    DemoSymbol("COST", "Costco", "Consumer", display_order=100),
    DemoSymbol("CAT", "Caterpillar", "Industrials", display_order=110),
    DemoSymbol("GE", "GE Aerospace", "Industrials", display_order=120),
    DemoSymbol("SPY", "S&P 500 ETF", "Broad Market", asset_type="etf", display_order=130),
    DemoSymbol("QQQ", "Nasdaq-100 ETF", "Broad Market", asset_type="etf", display_order=140),
)


def demo_symbols(*, enabled_only: bool = True) -> list[DemoSymbol]:
    rows = [row for row in _DEMO_SYMBOLS if row.enabled or not enabled_only]
    return sorted(rows, key=lambda row: (row.display_order, row.ticker))


def demo_tickers(*, enabled_only: bool = True) -> tuple[str, ...]:
    return tuple(row.ticker for row in demo_symbols(enabled_only=enabled_only))


def is_demo_ticker(ticker: str) -> bool:
    symbol = str(ticker or "").upper().strip()
    return symbol in set(demo_tickers())


def demo_groups() -> dict[str, list[DemoSymbol]]:
    groups: dict[str, list[DemoSymbol]] = {}
    for row in demo_symbols():
        groups.setdefault(row.category, []).append(row)
    return groups


def as_public_rows() -> list[dict]:
    return [
        {
            "ticker": row.ticker,
            "display_name": row.display_name,
            "category": row.category,
            "asset_type": row.asset_type,
            "display_order": row.display_order,
            "refresh_policy": row.refresh_policy,
        }
        for row in demo_symbols()
    ]
