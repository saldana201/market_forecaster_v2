from __future__ import annotations

from types import SimpleNamespace
import numpy as np
import pandas as pd

from market_forecaster.core.forecast_audit import (
    INCUMBENT_CANDIDATE,
    build_consensus_audit_record,
    governance_summary,
    load_audit_outcomes,
    load_audit_runs,
    persist_audit_run,
    reconcile_matured_outcomes,
)


def _result():
    dates = pd.bdate_range("2026-01-06", periods=20)
    ensemble = np.linspace(101, 110, 20)
    base = ensemble * 1.002
    final = base * 1.001
    return SimpleNamespace(
        dates=dates,
        ensemble=ensemble,
        base_consensus=base,
        consensus=final,
        lower=final * 0.95,
        upper=final * 1.05,
        xgb_anchors=[],
        options_anchors=[],
        current_regime="RANGE",
        base_status="XGB_GATED_CONSENSUS",
        status="OPTIONS_ADAPTIVE_CONSENSUS",
    )


def _stock(periods=30):
    dates = pd.bdate_range("2026-01-05", periods=periods)
    return pd.DataFrame({"Date": dates, "Close": np.linspace(100, 115, periods)})


def test_exact_rerun_is_deduplicated(tmp_path):
    record = build_consensus_audit_record(
        "TEST", _result(), {"models_used": ["ridge"], "weights": {"ridge": 1.0}},
        _stock(), app_version="2.9.0",
    )
    assert persist_audit_run(record, base_dir=tmp_path)
    assert not persist_audit_run(record, base_dir=tmp_path)
    assert len(load_audit_runs("TEST", base_dir=tmp_path)) == 1


def test_matured_target_creates_separate_outcome_ledger(tmp_path):
    record = build_consensus_audit_record(
        "TEST", _result(), {"models_used": ["ridge"]},
        pd.DataFrame({"Date": [pd.Timestamp("2026-01-05")], "Close": [100.0]}),
        app_version="2.9.0",
    )
    persist_audit_run(record, base_dir=tmp_path)
    summary = reconcile_matured_outcomes("TEST", _stock(), base_dir=tmp_path)
    assert summary["created"] >= 1
    assert load_audit_outcomes("TEST", base_dir=tmp_path)
    assert "realized_price" not in load_audit_runs("TEST", base_dir=tmp_path)[0]


def test_future_target_stays_pending(tmp_path):
    origin = pd.DataFrame({"Date": [pd.Timestamp("2026-01-05")], "Close": [100.0]})
    record = build_consensus_audit_record("TEST", _result(), {}, origin, app_version="2.9.0")
    persist_audit_run(record, base_dir=tmp_path)
    summary = reconcile_matured_outcomes("TEST", origin, base_dir=tmp_path)
    assert summary["created"] == 0
    assert summary["pending"] > 0


def test_governance_collects_until_minimum_evidence():
    runs = [{"run_id": "r1", "market_last_timestamp": "2026-01-01", "created_at_utc": "2026-01-01T12:00:00Z"}]
    outcomes = [{
        "run_id": "r1", "horizon": 1,
        "candidate_scores": {
            INCUMBENT_CANDIDATE: {
                "absolute_return_error": 0.01, "price_pct_error": 1.0, "direction_correct": True
            }
        },
    }]
    assert governance_summary(runs, outcomes, min_observations=5, min_unique_runs=2)["status"] == "COLLECTING"


def test_challenger_can_be_recommended_but_not_auto_promoted():
    runs, outcomes = [], []
    for i in range(10):
        run_id = f"r{i}"
        runs.append({
            "run_id": run_id,
            "market_last_timestamp": f"2026-01-{i+1:02d}",
            "created_at_utc": f"2026-01-{i+1:02d}T12:00:00Z",
        })
        outcomes.append({
            "run_id": run_id, "horizon": 1,
            "candidate_scores": {
                INCUMBENT_CANDIDATE: {
                    "absolute_return_error": 0.020, "price_pct_error": 2.0, "direction_correct": True
                },
                "validated_ensemble": {
                    "absolute_return_error": 0.010, "price_pct_error": 1.0, "direction_correct": True
                },
            },
        })
    summary = governance_summary(
        runs, outcomes, min_observations=5, min_unique_runs=5, challenger_margin_pct=5.0
    )
    assert summary["status"] == "CHALLENGER_LEADS"
    assert summary["observed_leader"] == "validated_ensemble"
    assert summary["recommendation"] == "REVIEW_CHALLENGER_PROMOTION"
    assert summary["policy"] == "advisory_only_no_auto_promotion_in_v2_9"


def test_same_market_snapshot_uses_latest_run_only():
    runs = [
        {"run_id": "old", "market_last_timestamp": "2026-01-01", "created_at_utc": "2026-01-01T12:00:00Z"},
        {"run_id": "new", "market_last_timestamp": "2026-01-01", "created_at_utc": "2026-01-01T13:00:00Z"},
    ]
    outcomes = [
        {"run_id": "old", "horizon": 1, "candidate_scores": {
            INCUMBENT_CANDIDATE: {"absolute_return_error": 0.50, "price_pct_error": 50, "direction_correct": False}
        }},
        {"run_id": "new", "horizon": 1, "candidate_scores": {
            INCUMBENT_CANDIDATE: {"absolute_return_error": 0.01, "price_pct_error": 1, "direction_correct": True}
        }},
    ]
    summary = governance_summary(runs, outcomes, min_observations=1, min_unique_runs=1)
    row = next(x for x in summary["leaderboard"] if x["candidate"] == INCUMBENT_CANDIDATE)
    assert row["observations"] == 1
    assert abs(row["mae_return_bps"] - 100.0) < 1e-9
