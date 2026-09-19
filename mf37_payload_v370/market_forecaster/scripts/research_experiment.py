"""Run the v3.7 Model Tournament from the command line."""
from __future__ import annotations

import argparse
import json

from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.feature_store import build_feature_store
from market_forecaster.core.experiment_runner import DEFAULT_MODELS, run_research_experiment
from market_forecaster.core.model_tournament import model_registry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--period", default="5y")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--test-size", type=int, default=20)
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS))
    parser.add_argument("--sequence-lookback", type=int, default=20)
    parser.add_argument("--deep-epochs", type=int, default=15)
    parser.add_argument("--list-models", action="store_true")
    args = parser.parse_args()

    if args.list_models:
        print(json.dumps(model_registry(), indent=2))
        return

    ticker = args.ticker.upper().strip()
    frame = fetch_stock_data(ticker, args.period, "1d")
    if frame.empty:
        raise SystemExit(f"No data available for {ticker}")

    features, metadata = build_feature_store(frame, ticker)
    result = run_research_experiment(
        features,
        models=[x.strip().lower() for x in args.models.split(",") if x.strip()],
        n_splits=args.folds,
        test_size=args.test_size,
        sequence_lookback=args.sequence_lookback,
        deep_epochs=args.deep_epochs,
    )
    result["ticker"] = ticker
    result["dataset_metadata"] = metadata.to_dict()
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
