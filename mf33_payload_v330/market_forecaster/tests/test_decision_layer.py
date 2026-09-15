from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from market_forecaster.core import decision_layer as dl


def _stock(price=100.0, cached=False, failover=False):
    df = pd.DataFrame({
        "Date": pd.bdate_range("2026-01-01", periods=60),
        "Close": [price] * 60,
    })
    df.attrs["is_cached"] = cached
    df.attrs["degraded_data"] = cached or failover
    df.attrs["provider_failover_used"] = failover
    return df


def _deployment(targets=None, lower=None, upper=None, drift="HEALTHY"):
    targets = targets if targets is not None else np.linspace(101, 120, 20)
    lower = lower if lower is not None else np.linspace(96, 90, 20)
    upper = upper if upper is not None else np.linspace(108, 135, 20)
    return SimpleNamespace(
        effective_champion="adaptive_production_consensus",
        policy_status="DEFAULT_INCUMBENT",
        drift_status=drift,
        dates=pd.bdate_range("2026-04-01", periods=20),
        path=np.asarray(targets, dtype=float),
        lower=np.asarray(lower, dtype=float),
        upper=np.asarray(upper, dtype=float),
    )


def _history(n, horizon=20, predicted=0.10, realized=0.14):
    runs, outcomes = [], []
    for i in range(n):
        run_id = f"r{i}"
        runs.append({
            "run_id": run_id,
            "market_last_timestamp": f"2026-01-{(i % 28) + 1:02d}",
            "created_at_utc": f"2026-02-{(i % 28) + 1:02d}T12:00:00Z",
        })
        outcomes.append({
            "run_id": run_id,
            "horizon": horizon,
            "realized_return": realized,
            "candidate_scores": {
                "adaptive_production_consensus": {
                    "predicted_return": predicted,
                    "absolute_return_error": abs(realized - predicted),
                }
            },
        })
    return runs, outcomes


def test_provisional_has_no_numeric_probability():
    result = dl.build_decision_layer("TEST", _deployment(), _stock(), runs=[], outcomes=[])
    row = next(x for x in result.horizons if x.horizon == 20)
    assert row.evidence_status == "PROVISIONAL"
    assert row.probability_up_pct is None
    assert not row.actionable


def test_low_sample_probability_is_shrunk_toward_fifty():
    runs, outcomes = _history(10)
    result = dl.build_decision_layer("TEST", _deployment(), _stock(), runs=runs, outcomes=outcomes)
    row = next(x for x in result.horizons if x.horizon == 20)
    assert row.evidence_status == "LOW_SAMPLE"
    assert row.probability_up_pct is not None
    assert 50.0 < row.probability_up_pct < 100.0
    assert not row.actionable


def test_calibrated_bullish_setup_can_be_actionable():
    runs, outcomes = _history(25, predicted=0.10, realized=0.14)
    result = dl.build_decision_layer("TEST", _deployment(), _stock(), runs=runs, outcomes=outcomes)
    row = next(x for x in result.horizons if x.horizon == 20)
    assert row.evidence_status == "CALIBRATED"
    assert row.probability_up_pct >= 58.0
    assert row.reward_risk is not None and row.reward_risk >= 1.5
    assert row.recommendation == "LONG_SETUP"
    assert row.actionable


def test_cached_data_blocks_actionable_setup():
    runs, outcomes = _history(25, predicted=0.10, realized=0.14)
    result = dl.build_decision_layer("TEST", _deployment(), _stock(cached=True), runs=runs, outcomes=outcomes)
    row = next(x for x in result.horizons if x.horizon == 20)
    assert row.evidence_status == "CALIBRATED"
    assert row.recommendation == "WAIT"
    assert not row.actionable
    assert row.opportunity_score <= 20.0


def test_severe_drift_blocks_actionable_setup():
    runs, outcomes = _history(25, predicted=0.10, realized=0.14)
    result = dl.build_decision_layer("TEST", _deployment(drift="DEGRADED"), _stock(), runs=runs, outcomes=outcomes)
    row = next(x for x in result.horizons if x.horizon == 20)
    assert row.recommendation == "WAIT"
    assert not row.actionable


def test_snapshot_roundtrip(tmp_path):
    result = dl.build_decision_layer("TEST", _deployment(), _stock(), runs=[], outcomes=[])
    dl.persist_decision_snapshot(result, base_dir=tmp_path)
    loaded = dl.load_decision_snapshot("TEST", base_dir=tmp_path)
    assert loaded["ticker"] == "TEST"
    assert loaded["primary_horizon"] is not None
