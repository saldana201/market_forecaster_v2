from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from market_forecaster.core import opportunity_ranking as ranking

NOW = datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc)


def _snapshot(
    ticker,
    *,
    evidence="CALIBRATED",
    score=80.0,
    recommendation="LONG_SETUP",
    actionable=True,
    data_mode="LIVE_PRIMARY",
    drift="HEALTHY",
    generated="2026-09-15T00:00:00+00:00",
):
    return {
        "ticker": ticker,
        "effective_champion": "adaptive_production_consensus",
        "policy_status": "DEFAULT_INCUMBENT",
        "drift_status": drift,
        "data_mode": data_mode,
        "generated_at_utc": generated,
        "primary_horizon": 20,
        "primary_recommendation": recommendation,
        "horizons": [{
            "horizon": 20,
            "target_date": "2026-10-01T00:00:00",
            "evidence_status": evidence,
            "resolved_observations": 25 if evidence == "CALIBRATED" else 10,
            "unique_market_snapshots": 8,
            "calibrated_expected_return_pct": 8.0,
            "probability_up_pct": 65.0 if evidence != "PROVISIONAL" else None,
            "reward_risk": 2.0,
            "reference_entry": 100.0,
            "decision_target": 108.0,
            "invalidation": 96.0,
            "opportunity_score": score,
            "direction": "BULLISH",
            "recommendation": recommendation,
            "actionable": actionable,
        }],
    }


def test_watchlist_normalizes_and_deduplicates():
    assert ranking.normalize_watchlist("spy, AAPL;spy  tmc") == ["SPY", "AAPL", "TMC"]


def test_calibrated_evidence_ranks_above_provisional(monkeypatch):
    snapshots = {
        "AAA": _snapshot("AAA", evidence="CALIBRATED", score=60),
        "BBB": _snapshot("BBB", evidence="PROVISIONAL", score=90, actionable=False, recommendation="RESEARCH_BULLISH"),
    }
    monkeypatch.setattr(ranking, "load_decision_snapshot", lambda t, base_dir=None: snapshots.get(t, {}))
    result = ranking.rank_watchlist(
        ["AAA", "BBB"], include_correlation=False, now=NOW
    )
    assert result["ranked"][0]["ticker"] == "AAA"


def test_missing_decision_is_reported(monkeypatch):
    monkeypatch.setattr(ranking, "load_decision_snapshot", lambda t, base_dir=None: {})
    result = ranking.rank_watchlist(["AAA"], include_correlation=False, now=NOW)
    assert result["coverage_count"] == 0
    assert result["missing_decisions"] == ["AAA"]


def test_stale_snapshot_gets_penalized(monkeypatch):
    snapshots = {
        "FRESH": _snapshot("FRESH", score=70, generated="2026-09-15T00:00:00+00:00"),
        "STALE": _snapshot("STALE", score=70, generated="2026-09-01T00:00:00+00:00"),
    }
    monkeypatch.setattr(ranking, "load_decision_snapshot", lambda t, base_dir=None: snapshots.get(t, {}))
    result = ranking.rank_watchlist(
        ["FRESH", "STALE"], include_correlation=False, now=NOW
    )
    assert result["ranked"][0]["ticker"] == "FRESH"
    stale = next(x for x in result["ranked"] if x["ticker"] == "STALE")
    assert stale["staleness_multiplier"] == 0.40


def test_high_same_direction_correlation_reduces_second_score(monkeypatch):
    snapshots = {
        "AAA": _snapshot("AAA", score=80),
        "BBB": _snapshot("BBB", score=75),
    }
    monkeypatch.setattr(ranking, "load_decision_snapshot", lambda t, base_dir=None: snapshots.get(t, {}))
    monkeypatch.setattr(
        ranking,
        "build_return_correlation",
        lambda tickers, period="6mo": (
            {"AAA": {"AAA": 1.0, "BBB": 0.95}, "BBB": {"AAA": 0.95, "BBB": 1.0}},
            {"AAA": 100, "BBB": 100},
        ),
    )
    result = ranking.rank_watchlist(["AAA", "BBB"], include_correlation=True, now=NOW)
    bbb = next(x for x in result["ranked"] if x["ticker"] == "BBB")
    assert bbb["correlation_multiplier"] < 1.0
    assert bbb["ranking_score"] < bbb["base_adjusted_score"]


def test_research_risk_budget_is_capped(monkeypatch):
    snapshots = {
        "AAA": _snapshot("AAA", score=90),
        "BBB": _snapshot("BBB", score=80),
        "CCC": _snapshot("CCC", score=70),
    }
    monkeypatch.setattr(ranking, "load_decision_snapshot", lambda t, base_dir=None: snapshots.get(t, {}))
    result = ranking.rank_watchlist(
        list(snapshots), include_correlation=False, max_single_risk_budget_pct=25, now=NOW
    )
    assert all(row["research_risk_budget_pct"] <= 25.0 for row in result["ranked"])
    assert result["unallocated_research_risk_budget_pct"] >= 25.0


def test_correlated_name_gets_lower_risk_budget_cap(monkeypatch):
    snapshots = {
        "AAA": _snapshot("AAA", score=90),
        "BBB": _snapshot("BBB", score=80),
    }
    monkeypatch.setattr(ranking, "load_decision_snapshot", lambda t, base_dir=None: snapshots.get(t, {}))
    monkeypatch.setattr(
        ranking,
        "build_return_correlation",
        lambda tickers, period="6mo": (
            {"AAA": {"AAA": 1.0, "BBB": 0.90}, "BBB": {"AAA": 0.90, "BBB": 1.0}},
            {"AAA": 100, "BBB": 100},
        ),
    )
    result = ranking.rank_watchlist(["AAA", "BBB"], include_correlation=True, now=NOW)
    bbb = next(x for x in result["ranked"] if x["ticker"] == "BBB")
    assert bbb["research_risk_budget_pct"] <= 15.0


def test_watchlist_roundtrip(tmp_path):
    saved = ranking.save_watchlist(["SPY", "AAPL", "SPY"], base_dir=tmp_path)
    assert saved == ["SPY", "AAPL"]
    assert ranking.load_watchlist(base_dir=tmp_path) == ["SPY", "AAPL"]
