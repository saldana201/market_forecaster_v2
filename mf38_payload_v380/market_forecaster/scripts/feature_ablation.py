"""Run Market Forecaster 3.8 feature-family ablations from the CLI."""
from __future__ import annotations

import argparse
import json

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.feature_store import build_feature_store
from market_forecaster.core.feature_ablation import (
    DEFAULT_ABLATION_MODELS,
    run_feature_ablation,
)
from market_forecaster.core.market_context import (
    DEFAULT_CONTEXT_FAMILIES,
    build_market_context,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--period", default="5y")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--test-size", type=int, default=20)
    parser.add_argument("--families", default=",".join(DEFAULT_CONTEXT_FAMILIES))
    parser.add_argument("--models", default=",".join(DEFAULT_ABLATION_MODELS))
    parser.add_argument("--sector-ticker", default="")
    args = parser.parse_args()

    ticker = args.ticker.upper().strip()
    families = [x.strip().lower() for x in args.families.split(",") if x.strip()]
    models = [x.strip().lower() for x in args.models.split(",") if x.strip()]

    market = fetch_stock_data(ticker, args.period, "1d")
    if market.empty:
        raise SystemExit(f"No data available for {ticker}")

    base, metadata = build_feature_store(market, ticker)
    enriched, registry = build_market_context(
        base,
        ticker,
        period=args.period,
        families=families,
        sector_ticker=args.sector_ticker or None,
    )
    result = run_feature_ablation(
        base,
        enriched,
        registry,
        families=families,
        models=models,
        n_splits=args.folds,
        test_size=args.test_size,
    )
    result["ticker"] = ticker
    result["dataset_metadata"] = metadata.to_dict()
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
