from __future__ import annotations
import numpy as np
import pandas as pd

import market_forecaster.core.feature_ablation as ablation


def _frame():
    dates = pd.bdate_range("2025-01-01", periods=100)
    return pd.DataFrame({
        "Date": dates,
        "Close": np.linspace(100, 120, len(dates)),
        "ticker": "TEST",
        "feature_asof": dates,
        "feature_schema_version": "test-v1",
        "base_feature": np.linspace(0, 1, len(dates)),
        "ctx_broad_market_spy_ret_5": np.linspace(-0.1, 0.1, len(dates)),
        "target_log_return_5d": 0.01,
        "target_end_date_5d": dates + pd.offsets.BDay(5),
    })


def _fake_result(frame, **kwargs):
    improved = any(c.startswith("ctx_broad_market_") for c in frame.columns)
    mae = 90.0 if improved else 100.0
    folds = []
    for fold in (1, 2, 3):
        train_date = pd.Timestamp("2025-04-01") + pd.offsets.BDay(fold)
        test_date = pd.Timestamp("2025-04-15") + pd.offsets.BDay(fold)
        for model in ("zero_return", "ridge"):
            m = 110.0 if model == "zero_return" else mae
            folds.append({
                "horizon": 5,
                "fold": fold,
                "model": model,
                "train_last_date": train_date.isoformat(),
                "test_first_date": test_date.isoformat(),
                "return_mae_bps": m,
                "test_rows": 20,
            })
    return {
        "folds": folds,
        "summaries": [
            {"horizon": 5, "model": "zero_return", "directional_accuracy_pct": 50.0},
            {"horizon": 5, "model": "ridge", "directional_accuracy_pct": 55.0},
        ],
    }


def test_feature_view_includes_only_selected_context():
    frame = _frame()
    frame["ctx_rates_tnx_level"] = 4.2
    view = ablation._feature_view(
        frame, ["base_feature", "ctx_broad_market_spy_ret_5"]
    )
    assert "ctx_broad_market_spy_ret_5" in view.columns
    assert "ctx_rates_tnx_level" not in view.columns
    assert "target_log_return_5d" in view.columns


def test_positive_family_lift_becomes_supported(monkeypatch):
    monkeypatch.setattr(ablation, "run_research_experiment", _fake_result)
    monkeypatch.setattr(
        ablation,
        "paired_fold_improvement",
        lambda candidate, baseline, seed=42: {
            "mean_improvement_pct": 10.0,
            "ci_low_pct": 5.0,
            "ci_high_pct": 15.0,
        },
    )
    frame = _frame()
    base = frame.drop(columns=["ctx_broad_market_spy_ret_5"])
    registry = {
        "broad_market": {
            "available": True,
            "columns": ["ctx_broad_market_spy_ret_5"],
            "coverage_pct": 100.0,
        }
    }
    result = ablation.run_feature_ablation(
        base, frame, registry,
        families=["broad_market"],
        models=["ridge"],
        horizons=[5],
        n_splits=3,
        test_size=20,
    )
    row = result["comparisons"][0]
    assert row["evidence_status"] == "SUPPORTED"
    assert row["mae_lift_pct"] == 10.0
    assert result["family_summaries"][0]["status"] == "EVIDENCE_FOUND"


def test_unavailable_family_is_reported_without_run(monkeypatch):
    monkeypatch.setattr(ablation, "run_research_experiment", _fake_result)
    frame = _frame()
    base = frame.drop(columns=["ctx_broad_market_spy_ret_5"])
    registry = {
        "volatility": {
            "available": False,
            "columns": [],
            "coverage_pct": 0.0,
        }
    }
    result = ablation.run_feature_ablation(
        base, frame, registry,
        families=["volatility"],
        models=["ridge"],
        horizons=[5],
    )
    assert result["family_summaries"][0]["status"] == "UNAVAILABLE"
    assert not result["comparisons"]


def test_protocol_mismatch_blocks_lift(monkeypatch):
    calls = {"n": 0}
    def fake(frame, **kwargs):
        calls["n"] += 1
        result = _fake_result(frame, **kwargs)
        if calls["n"] > 1:
            result["folds"][0]["test_first_date"] = "2099-01-01T00:00:00"
        return result
    monkeypatch.setattr(ablation, "run_research_experiment", fake)

    frame = _frame()
    base = frame.drop(columns=["ctx_broad_market_spy_ret_5"])
    registry = {
        "broad_market": {
            "available": True,
            "columns": ["ctx_broad_market_spy_ret_5"],
            "coverage_pct": 100.0,
        }
    }
    result = ablation.run_feature_ablation(
        base, frame, registry,
        families=["broad_market"],
        models=["ridge"],
        horizons=[5],
    )
    assert result["family_summaries"][0]["status"] == "PROTOCOL_MISMATCH"
    assert not result["comparisons"]
