"""Generate the canonical Market Forecaster 4.0 Forecast Contract."""
from __future__ import annotations

import argparse
import json

from market_forecaster.core.forecast_contract import build_forecast_contract


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--period", default="10y")
    parser.add_argument("--folds", type=int, default=6)
    parser.add_argument("--test-size", type=int, default=20)
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()

    contract = build_forecast_contract(
        args.ticker,
        period=args.period,
        n_splits=args.folds,
        test_size=args.test_size,
        persist=args.persist,
    )
    print(json.dumps(contract, indent=2, default=str))


if __name__ == "__main__":
    main()
