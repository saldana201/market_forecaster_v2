"""Cross-ticker validation for a Forecast Authority configuration."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np

from market_forecaster.core.forecast_contract import build_forecast_contract


def _mean(values):
    clean = [float(x) for x in values if x is not None and np.isfinite(float(x))]
    return float(np.mean(clean)) if clean else None


def validate_authority_across_tickers(
    tickers: list[str],
    *,
    period: str = "10y",
    authority_config: dict | None = None,
    n_splits: int = 6,
    test_size: int = 20,
    repo_root: str | Path | None = None,
    contract_builder=build_forecast_contract,
) -> dict:
    symbols = []
    for ticker in tickers:
        symbol = str(ticker or "").upper().strip()
        if symbol and symbol not in symbols:
            symbols.append(symbol)

    if not symbols:
        raise ValueError("At least one ticker is required")

    ticker_results = []
    flat = []

    for symbol in symbols:
        try:
            contract = contract_builder(
                symbol,
                period=period,
                authority_config=authority_config,
                n_splits=n_splits,
                test_size=test_size,
                persist=False,
                repo_root=repo_root,
            )
            ticker_results.append({
                "ticker": symbol,
                "status": contract.get("status"),
                "contract_id": contract.get("contract_id"),
                "errors": contract.get("errors", []),
            })

            for forecast in contract.get("forecasts", []):
                diag = forecast.get("diagnostics", {})
                flat.append({
                    "ticker": symbol,
                    "horizon_days": int(forecast["horizon_days"]),
                    "model": forecast.get("model"),
                    "context_family": forecast.get("context_family"),
                    "calibration_status": forecast.get("calibration_status"),
                    "calibration_samples": int(forecast.get("calibration_samples", 0) or 0),
                    "brier_score": diag.get("brier_score"),
                    "brier_skill_vs_50_pct": diag.get("brier_skill_vs_50_pct"),
                    "expected_calibration_error": diag.get("expected_calibration_error"),
                    "coverage_80_pct": diag.get("coverage_80_pct"),
                    "coverage_90_pct": diag.get("coverage_90_pct"),
                })
        except Exception as exc:
            ticker_results.append({
                "ticker": symbol,
                "status": "ERROR",
                "contract_id": None,
                "errors": [{"error": str(exc)}],
            })

    grouped = defaultdict(list)
    for row in flat:
        grouped[(row["horizon_days"], row["model"], row["context_family"])].append(row)

    summaries = []
    for (horizon, model, context), rows in sorted(grouped.items()):
        summaries.append({
            "horizon_days": int(horizon),
            "model": model,
            "context_family": context,
            "tickers_with_forecast": len({r["ticker"] for r in rows}),
            "calibrated_tickers": sum(r["calibration_status"] == "CALIBRATED" for r in rows),
            "mean_calibration_samples": _mean([r["calibration_samples"] for r in rows]),
            "mean_brier_score": _mean([r["brier_score"] for r in rows]),
            "mean_brier_skill_vs_50_pct": _mean([r["brier_skill_vs_50_pct"] for r in rows]),
            "mean_expected_calibration_error": _mean([r["expected_calibration_error"] for r in rows]),
            "mean_coverage_80_pct": _mean([r["coverage_80_pct"] for r in rows]),
            "mean_coverage_90_pct": _mean([r["coverage_90_pct"] for r in rows]),
        })

    return {
        "protocol_version": "4.0-cross-ticker-authority-validation-v1",
        "tickers_requested": symbols,
        "tickers_completed": sum(row["status"] in {"READY", "PARTIAL"} for row in ticker_results),
        "ticker_results": ticker_results,
        "forecast_rows": flat,
        "summaries": summaries,
        "notes": [
            "This is descriptive cross-ticker evidence for the explicit Forecast Authority configuration.",
            "The validator does not change the authority configuration or production deployment state.",
            "Calibration and coverage metrics come from each ticker's prior out-of-sample forecast history.",
        ],
    }
