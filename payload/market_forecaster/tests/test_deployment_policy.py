from __future__ import annotations

from types import SimpleNamespace
import json

import numpy as np
import pandas as pd

from market_forecaster.core.deployment_policy import (
    DEFAULT_CHAMPION,
    approve_champion,
    build_deployment_decision,
    deployment_policy_state,
    drift_report,
    load_governance_events,
    validate_champion_approval,
)


def _runs(n=30):
    rows = []
    for i in range(n):
        rows.append({
            "run_id": f"r{i}",
            "market_last_timestamp": f"2026-01-{(i % 28) + 1:02d}T00:00:00",
            "created_at_utc": f"2026-02-{(i % 28) + 1:02d}T12:00:00Z",
            "current_regime": "RANGE",
        })
    return rows


def _outcomes_for_candidate(candidate, errors, *, direction=True):
    rows = []
    for i, err in enumerate(errors):
        rows.append({
            "run_id": f"r{i}",
            "horizon": 1,
            "realized_date": f"2026-03-{(i % 28) + 1:02d}",
            "candidate_scores": {
                candidate: {
                    "absolute_return_error": float(err),
                    "price_pct_error": float(err) * 100,
                    "direction_correct": direction if not isinstance(direction, list) else direction[i],
                }
            },
        })
    return rows


def _write_ledgers(base, runs, outcomes):
    (base / "runs").mkdir(parents=True, exist_ok=True)
    (base / "outcomes").mkdir(parents=True, exist_ok=True)
    with (base / "runs" / "TEST.jsonl").open("w", encoding="utf-8") as handle:
        for row in runs:
            handle.write(json.dumps(row) + "\n")
    with (base / "outcomes" / "TEST.jsonl").open("w", encoding="utf-8") as handle:
        for row in outcomes:
            handle.write(json.dumps(row) + "\n")


def test_drift_collects_without_reference_history():
    report = drift_report(
        _runs(8),
        _outcomes_for_candidate("validated_ensemble", [0.01] * 8),
    )
    row = next(x for x in report["summary"] if x["candidate"] == "validated_ensemble")
    assert row["status"] == "COLLECTING"


def test_bad_recent_challenger_is_frozen():
    errors = [0.01] * 20 + [0.03] * 10
    report = drift_report(
        _runs(30),
        _outcomes_for_candidate("validated_ensemble", errors),
    )
    row = next(x for x in report["summary"] if x["candidate"] == "validated_ensemble")
    assert row["status"] == "FROZEN"
    assert row["degradation_pct"] >= 50


def test_degraded_incumbent_alerts_but_is_not_auto_frozen():
    errors = [0.01] * 20 + [0.03] * 10
    report = drift_report(
        _runs(30),
        _outcomes_for_candidate(DEFAULT_CHAMPION, errors),
    )
    row = next(x for x in report["summary"] if x["candidate"] == DEFAULT_CHAMPION)
    assert row["status"] == "DEGRADED"


def _governance_dataset(challenger_error=0.01, incumbent_error=0.02):
    runs = _runs(30)
    outcomes = []
    for i in range(30):
        outcomes.append({
            "run_id": f"r{i}",
            "horizon": 1,
            "realized_date": f"2026-03-{(i % 28) + 1:02d}",
            "candidate_scores": {
                DEFAULT_CHAMPION: {
                    "absolute_return_error": incumbent_error,
                    "price_pct_error": incumbent_error * 100,
                    "direction_correct": True,
                },
                "validated_ensemble": {
                    "absolute_return_error": challenger_error,
                    "price_pct_error": challenger_error * 100,
                    "direction_correct": True,
                },
            },
        })
    return runs, outcomes


def test_challenger_approval_requires_governance_recommendation(tmp_path):
    ok, reason, _ = validate_champion_approval(
        "TEST",
        "validated_ensemble",
        "operator",
        "Strong enough rationale",
        base_dir=tmp_path,
        runs=_runs(10),
        outcomes=_outcomes_for_candidate("validated_ensemble", [0.01] * 10),
    )
    assert not ok
    assert reason


def test_healthy_governance_leader_can_be_explicitly_approved(tmp_path):
    runs, outcomes = _governance_dataset()
    _write_ledgers(tmp_path, runs, outcomes)

    event = approve_champion(
        "TEST",
        "validated_ensemble",
        "operator",
        "Validated ensemble materially leads realized outcomes",
        base_dir=tmp_path,
    )
    assert event["candidate"] == "validated_ensemble"
    assert load_governance_events("TEST", base_dir=tmp_path)

    state = deployment_policy_state("TEST", base_dir=tmp_path)
    assert state["approved_champion"] == "validated_ensemble"
    assert state["effective_champion"] == "validated_ensemble"


def test_frozen_approved_challenger_falls_back_to_incumbent(tmp_path):
    runs = _runs(30)
    outcomes = []
    for i in range(30):
        challenger_err = 0.01 if i < 20 else 0.04
        outcomes.append({
            "run_id": f"r{i}",
            "horizon": 1,
            "realized_date": f"2026-03-{(i % 28) + 1:02d}",
            "candidate_scores": {
                DEFAULT_CHAMPION: {
                    "absolute_return_error": 0.02,
                    "price_pct_error": 2.0,
                    "direction_correct": True,
                },
                "validated_ensemble": {
                    "absolute_return_error": challenger_err,
                    "price_pct_error": challenger_err * 100,
                    "direction_correct": True,
                },
            },
        })
    _write_ledgers(tmp_path, runs, outcomes)
    (tmp_path / "governance").mkdir(parents=True, exist_ok=True)
    approval = {
        "event_type": "APPROVE_CHAMPION",
        "ticker": "TEST",
        "candidate": "validated_ensemble",
        "approved_by": "operator",
        "rationale": "Previously healthy",
        "created_at_utc": "2026-03-01T00:00:00Z",
        "event_id": "evt1",
    }
    with (tmp_path / "governance" / "TEST.jsonl").open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(approval) + "\n")

    state = deployment_policy_state("TEST", base_dir=tmp_path)
    assert state["approved_champion"] == "validated_ensemble"
    assert state["effective_champion"] == DEFAULT_CHAMPION
    assert state["policy_status"] == "FROZEN_FALLBACK"


def test_deployment_decision_uses_effective_champion(tmp_path):
    dates = pd.bdate_range("2026-01-01", periods=20)
    result = SimpleNamespace(
        dates=dates,
        ensemble=np.full(20, 100.0),
        base_consensus=np.full(20, 105.0),
        consensus=np.full(20, 110.0),
        lower=np.full(20, 100.0),
        upper=np.full(20, 120.0),
    )
    (tmp_path / "governance").mkdir(parents=True, exist_ok=True)
    approval = {
        "event_type": "APPROVE_CHAMPION",
        "ticker": "TEST",
        "candidate": DEFAULT_CHAMPION,
        "approved_by": "operator",
        "rationale": "Keep the incumbent",
        "created_at_utc": "2026-03-01T00:00:00Z",
        "event_id": "evt2",
    }
    with (tmp_path / "governance" / "TEST.jsonl").open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(approval) + "\n")

    decision = build_deployment_decision("TEST", result, base_dir=tmp_path)
    assert decision.effective_champion == DEFAULT_CHAMPION
    assert np.allclose(decision.path, 110.0)
