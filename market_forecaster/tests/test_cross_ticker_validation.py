from __future__ import annotations

from market_forecaster.core.cross_ticker_validation import validate_authority_across_tickers


def _builder(ticker, **kwargs):
    base = 0.20 if ticker == "AAPL" else 0.24
    return {
        "status": "READY",
        "contract_id": ticker + "-id",
        "errors": [],
        "forecasts": [
            {
                "horizon_days": 5,
                "model": "xgboost",
                "context_family": "none",
                "calibration_status": "CALIBRATED",
                "calibration_samples": 100,
                "diagnostics": {
                    "brier_score": base,
                    "brier_skill_vs_50_pct": (1 - base / 0.25) * 100,
                    "expected_calibration_error": 0.05,
                    "coverage_80_pct": 80.0,
                    "coverage_90_pct": 90.0,
                },
            }
        ],
    }


def test_cross_ticker_validator_aggregates_descriptively():
    result = validate_authority_across_tickers(
        ["AAPL", "MSFT"],
        contract_builder=_builder,
    )
    assert result["tickers_completed"] == 2
    summary = result["summaries"][0]
    assert summary["horizon_days"] == 5
    assert summary["tickers_with_forecast"] == 2
    assert summary["calibrated_tickers"] == 2
    assert 0.20 <= summary["mean_brier_score"] <= 0.24
