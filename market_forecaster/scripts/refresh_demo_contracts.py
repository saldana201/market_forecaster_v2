"""Refresh shared cached Forecast Contracts for the curated 4.1.0 Demo universe."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from market_forecaster.core.demo_universe import demo_symbols
from market_forecaster.core.forecast_authority import load_authority_config
from market_forecaster.core.forecast_contract import build_forecast_contract
from market_forecaster.services.shared_contract_store import (
    SharedContractStoreError,
    publish_shared_contract,
    shared_write_configuration_status,
)


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
            shared_status = "SKIPPED"
            shared_error = None
            shared_ready, _shared_reason = shared_write_configuration_status()
            if shared_ready:
                try:
                    publish_shared_contract(contract)
                    shared_status = "PUBLISHED"
                except SharedContractStoreError as exc:
                    shared_status = "ERROR"
                    shared_error = str(exc)

            result_row = {
                "ticker": row.ticker,
                "status": "SUCCESS",
                "contract_id": contract.get("contract_id"),
                "generated_at": contract.get("generated_at"),
                "shared_publish_status": shared_status,
            }
            if shared_error:
                result_row["shared_publish_error"] = shared_error
            results.append(result_row)
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
