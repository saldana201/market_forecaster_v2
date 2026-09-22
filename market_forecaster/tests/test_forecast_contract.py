from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import market_forecaster.core.forecast_contract as contract_mod
from market_forecaster.core.forecast_authority import default_authority_config
from market_forecaster.core.forecast_contract import (
    assert_forecast_only_contract,
    build_forecast_contract,
)


def _market():
    dates = pd.bdate_range("2025-01-01", periods=300)
    close = np.linspace(100, 130, len(dates))
    df = pd.DataFrame({
        "Date": dates,
        "Open": close,
        "High": close + 1,
        "Low": close - 1,
        "Close": close,
        "Volume": 1_000_000,
    })
    df.attrs["provider"] = "test-provider"
    return df


def _base_frame():
    dates = pd.bdate_range("2025-01-01", periods=300)
    close = np.linspace(100, 130, len(dates))
    frame = pd.DataFrame({
        "Date": dates,
        "Close": close,
        "feature_asof": dates,
        "feature_schema_version": "test-feature-v1",
        "base_feature": np.linspace(0, 1, len(dates)),
    })
    for horizon in (1, 5, 10, 20):
        frame[f"target_log_return_{horizon}d"] = 0.01
        frame[f"target_end_date_{horizon}d"] = dates + pd.offsets.BDay(horizon)
    return frame


def _metadata():
    return SimpleNamespace(
        provider="test-provider",
        provider_failover_used=False,
        cache_used=False,
        row_count=300,
        dataset_hash="hash123",
        schema_version="test-feature-v1",
    )


def _uncertainty(frame, *, ticker, model, horizons, **kwargs):
    horizon_values = [int(h) for h in horizons]
    return {
        "feature_schema_version": "test-feature-v1",
        "current_forecasts": [
            {
                "horizon": horizon,
                "target_date": f"2026-10-{horizon:02d}T00:00:00",
                "predicted_return": 0.01 * horizon / 5,
                "predicted_return_pct": 2.0,
                "predicted_price": 132.0,
                "prob_up_pct": 60.0,
                "calibration_status": "CALIBRATED",
                "calibration_samples": 100,
                "lower_price_80": 125.0,
                "upper_price_80": 138.0,
                "lower_price_90": 122.0,
                "upper_price_90": 141.0,
                "lower_return_pct_80": -2.0,
                "upper_return_pct_80": 6.0,
                "lower_return_pct_90": -4.0,
                "upper_return_pct_90": 8.0,
            }
            for horizon in horizon_values
        ],
        "calibration_summaries": [
            {
                "horizon": horizon,
                "oos_records": 120,
                "probability_eval_records": 80,
                "brier_score": 0.22,
                "brier_skill_vs_50_pct": 12.0,
                "expected_calibration_error": 0.05,
                "coverage_80_pct": 81.0,
                "coverage_90_pct": 91.0,
                "avg_width_bps_80": 500.0,
                "avg_width_bps_90": 700.0,
            }
            for horizon in horizon_values
        ],
    }


def test_contract_rejects_execution_semantics():
    with pytest.raises(ValueError):
        assert_forecast_only_contract({
            "ticker": "AAPL",
            "forecasts": [{"position_size": 0.2}],
        })


def test_contract_routes_each_horizon_through_explicit_authority(monkeypatch, tmp_path):
    monkeypatch.setattr(contract_mod, "fetch_stock_data", lambda *args, **kwargs: _market())
    monkeypatch.setattr(
        contract_mod,
        "build_feature_store",
        lambda market, symbol: (_base_frame(), _metadata()),
    )
    calls = []
    def fake_uncertainty(frame, **kwargs):
        calls.append((kwargs["model"], int(list(kwargs["horizons"])[0])))
        return _uncertainty(frame, **kwargs)
    monkeypatch.setattr(contract_mod, "run_uncertainty_research", fake_uncertainty)

    config = default_authority_config()
    config["horizons"]["1"]["model"] = "ridge"
    config["horizons"]["5"]["model"] = "xgboost"
    config["horizons"]["10"]["model"] = "hist_gradient_boosting"
    config["horizons"]["20"]["model"] = "random_forest"

    result = build_forecast_contract(
        "AAPL",
        authority_config=config,
        persist=False,
        repo_root=tmp_path,
        generated_at="2026-09-19T18:30:00+00:00",
    )
    assert result["status"] == "READY"
    assert [x["horizon_days"] for x in result["forecasts"]] == [1, 5, 10, 20]
    assert calls == [
        ("ridge", 1),
        ("xgboost", 5),
        ("hist_gradient_boosting", 10),
        ("random_forest", 20),
    ]
    assert result["scope"] == "FORECAST_ONLY"
    assert "position_size" not in str(result).lower()


def test_contract_groups_identical_authority_horizons_into_one_research_run(monkeypatch, tmp_path):
    monkeypatch.setattr(contract_mod, "fetch_stock_data", lambda *args, **kwargs: _market())
    monkeypatch.setattr(
        contract_mod,
        "build_feature_store",
        lambda market, symbol: (_base_frame(), _metadata()),
    )
    calls = []

    def fake_uncertainty(frame, **kwargs):
        calls.append((kwargs["model"], tuple(int(h) for h in kwargs["horizons"])))
        return _uncertainty(frame, **kwargs)

    monkeypatch.setattr(contract_mod, "run_uncertainty_research", fake_uncertainty)

    result = build_forecast_contract(
        "AAPL",
        authority_config=default_authority_config(),
        persist=False,
        repo_root=tmp_path,
    )

    assert result["status"] == "READY"
    assert [x["horizon_days"] for x in result["forecasts"]] == [1, 5, 10, 20]
    assert calls == [("xgboost", (1, 5, 10, 20))]


def test_unavailable_configured_context_fails_horizon_instead_of_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(contract_mod, "fetch_stock_data", lambda *args, **kwargs: _market())
    monkeypatch.setattr(
        contract_mod,
        "build_feature_store",
        lambda market, symbol: (_base_frame(), _metadata()),
    )
    monkeypatch.setattr(
        contract_mod,
        "build_market_context",
        lambda frame, symbol, **kwargs: (
            frame,
            {"volatility": {
                "available": False,
                "coverage_pct": 0.0,
                "sources_used": [],
                "feature_count": 0,
            }},
        ),
    )
    monkeypatch.setattr(contract_mod, "run_uncertainty_research", _uncertainty)

    config = default_authority_config()
    config["horizons"]["5"]["context_family"] = "volatility"

    result = build_forecast_contract(
        "AAPL",
        authority_config=config,
        persist=False,
        repo_root=tmp_path,
    )
    assert result["status"] == "PARTIAL"
    assert 5 not in [x["horizon_days"] for x in result["forecasts"]]
    assert any(error["horizon_days"] == 5 for error in result["errors"])
