"""Refresh shared cached Forecast Contracts for the curated 4.1.0 Demo universe."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from market_forecaster.core.demo_universe import demo_symbols
from market_forecaster.core.forecast_authority import load_authority_config
from market_forecaster.core.forecast_contract import build_forecast_contract


def refresh_demo_contracts(*, period: str = "10y", folds: int = 6) -> dict:
    authority = load_authority_config(require_available_models=True)
    results = []
    for row in demo_symbols():
        try:
            contract = build_forecast_contract(
                row.ticker,
                period=period,
                authority_config=authority,
                n_splits=folds,
                test_size=20,
                persist=True,
            )
            results.append({
                "ticker": row.ticker,
                "status": "SUCCESS",
                "contract_id": contract.get("contract_id"),
                "generated_at": contract.get("generated_at"),
            })
        except Exception as exc:
            # Existing latest.json remains untouched when generation fails because
            # persistence happens only after a successfully built contract.
            results.append({"ticker": row.ticker, "status": "ERROR", "error": str(exc)})
    return {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "period": period,
        "folds": folds,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", default="10y")
    parser.add_argument("--folds", type=int, default=6)
    args = parser.parse_args()
    print(json.dumps(refresh_demo_contracts(period=args.period, folds=args.folds), indent=2))


if __name__ == "__main__":
    main()
