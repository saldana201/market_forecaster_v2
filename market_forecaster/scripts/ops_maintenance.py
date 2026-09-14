"""Scheduler-ready operations maintenance CLI."""
from __future__ import annotations

import argparse
import json

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.operations import (
    operations_health, record_operation_event, run_operations_cycle,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", required=True, help="Comma-separated tickers")
    parser.add_argument("--period", default="2y")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    results = []
    failed = False
    for raw in args.tickers.split(","):
        ticker = raw.strip().upper()
        if not ticker:
            continue
        try:
            stock_df = fetch_stock_data(ticker, args.period, "1d")
            if stock_df.empty:
                raise RuntimeError("provider returned no market data")
            record_operation_event(
                ticker, "data_fetch", "SUCCESS", "Scheduled market-data fetch completed",
                metadata={"period": args.period, "rows": len(stock_df)},
            )
            cycle = run_operations_cycle(ticker, stock_df, force=args.force)
            results.append({"ticker": ticker, "cycle": cycle,
                            "health": operations_health(ticker, stock_df)})
        except Exception as exc:
            failed = True
            record_operation_event(ticker, "maintenance", "ERROR",
                                   f"Scheduled maintenance failed: {exc}")
            results.append({"ticker": ticker, "error": str(exc)})

    print(json.dumps(results, indent=2, default=str))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
