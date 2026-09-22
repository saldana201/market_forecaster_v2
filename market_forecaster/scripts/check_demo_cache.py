"""Deployment/readiness check for the Market Forecaster Demo cache."""
from __future__ import annotations

import argparse
import json

from market_forecaster.services.forecast_access import demo_cache_status


def summarize_demo_cache(*, repo_root=None) -> dict:
    rows = demo_cache_status(repo_root=repo_root)
    ready = [row for row in rows if row.get("available")]
    missing = [row for row in rows if not row.get("available")]
    return {
        "ready": len(ready),
        "total": len(rows),
        "complete": len(ready) == len(rows),
        "ready_tickers": [row["ticker"] for row in ready],
        "missing_tickers": [row["ticker"] for row in missing],
        "symbols": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check cached Forecast Contracts for the Demo universe.")
    parser.add_argument(
        "--fail-if-incomplete",
        action="store_true",
        help="Exit non-zero unless every enabled Demo symbol has a cached contract.",
    )
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    summary = summarize_demo_cache()
    print(json.dumps(summary, indent=None if args.compact else 2, default=str))

    if args.fail_if_incomplete and not summary["complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
