"""Run Market Forecaster 3.9 probability calibration and uncertainty research."""
from __future__ import annotations

import argparse
import json

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.feature_store import build_feature_store
from market_forecaster.core.market_context import build_market_context
from market_forecaster.core.uncertainty_calibration import run_uncertainty_research


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--period", default="10y")
    parser.add_argument("--model", default="xgboost")
    parser.add_argument("--folds", type=int, default=6)
    parser.add_argument("--test-size", type=int, default=20)
    parser.add_argument("--calibration-window", default="120")
    parser.add_argument("--context-family", default="none")
    parser.add_argument("--sector-ticker", default="")
    parser.add_argument("--sequence-lookback", type=int, default=20)
    parser.add_argument("--deep-epochs", type=int, default=15)
    args = parser.parse_args()

    symbol = args.ticker.upper().strip()
    market = fetch_stock_data(symbol, args.period, "1d")
    if market.empty:
        raise SystemExit(f"No data available for {symbol}")

    frame, metadata = build_feature_store(market, symbol)
    context_used = "none"

    family = args.context_family.lower().strip()
    if family != "none":
        enriched, registry = build_market_context(
            frame,
            symbol,
            period=args.period,
            families=[family],
            sector_ticker=args.sector_ticker or None,
        )
        if registry.get(family, {}).get("available"):
            frame = enriched
            context_used = family

    window = (
        None
        if str(args.calibration_window).strip().lower() in {"all", "none", "0"}
        else int(args.calibration_window)
    )

    result = run_uncertainty_research(
        frame,
        ticker=symbol,
        model=args.model,
        n_splits=args.folds,
        test_size=args.test_size,
        calibration_window=window,
        sequence_lookback=args.sequence_lookback,
        deep_epochs=args.deep_epochs,
    )
    result["dataset_metadata"] = metadata.to_dict()
    result["context_family"] = context_used
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
