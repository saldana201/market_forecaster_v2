"""Cross-ticker validation for the 4.0 Forecast Authority."""
from __future__ import annotations

import argparse
import json

from market_forecaster.core.cross_ticker_validation import validate_authority_across_tickers


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", default="AAPL,MSFT,SPY,QQQ,TSLA,TMC")
    parser.add_argument("--period", default="5y")
    parser.add_argument("--folds", type=int, default=4)
    parser.add_argument("--test-size", type=int, default=20)
    args = parser.parse_args()

    tickers = [x.strip().upper() for x in args.tickers.split(",") if x.strip()]
    result = validate_authority_across_tickers(
        tickers,
        period=args.period,
        n_splits=args.folds,
        test_size=args.test_size,
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
