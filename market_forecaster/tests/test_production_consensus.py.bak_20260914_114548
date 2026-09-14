import numpy as np
import pandas as pd

from market_forecaster.core.production_consensus import build_production_consensus


def _ensemble(n=20):
    base = np.linspace(100.0, 110.0, n)
    return {
        "ensemble": base,
        "dates": pd.date_range("2026-01-02", periods=n, freq="B"),
        "lower": base - 5,
        "upper": base + 5,
    }


def _xgb(forecasts, regime="TREND_UP"):
    return {
        "ticker": "TEST",
        "config": {"current_regime": regime},
        "forecasts": forecasts,
    }


def _forecast(h, price, global_gate="PASS", regime_gate="HOLD", matching=0):
    return {
        "horizon": h,
        "target_date": (pd.Timestamp("2026-01-02") + pd.offsets.BDay(h)).isoformat(),
        "bear_price": price * 0.94,
        "base_price": price,
        "bull_price": price * 1.06,
        "validation": {
            "production_gate": global_gate,
            "regime_gate": regime_gate,
            "regime_matching_folds": matching,
            "improvement_vs_baseline_pct": 10.0,
            "directional_accuracy_pct": 60.0,
            "interval_coverage_pct": 80.0,
        },
    }


def test_hold_horizon_cannot_move_production_consensus():
    ens = _ensemble()
    result = build_production_consensus(ens, _xgb([_forecast(5, 150.0, global_gate="HOLD")]), "TEST")
    assert result.status == "ENSEMBLE_ONLY"
    assert result.used_horizons == []
    assert np.allclose(result.consensus, ens["ensemble"])


def test_global_pass_without_regime_evidence_is_conservative():
    ens = _ensemble()
    result = build_production_consensus(ens, _xgb([_forecast(5, 120.0)]), "TEST")
    assert result.status == "XGB_GATED_CONSENSUS"
    assert result.used_horizons == [5]
    anchor = result.anchors[0]
    assert anchor.evidence_source == "global_pass_only"
    assert 0.10 <= anchor.blend_weight <= 0.15
    base_at_anchor = ens["ensemble"][4]
    consensus_at_anchor = result.consensus[4]
    assert base_at_anchor < consensus_at_anchor < 120.0


def test_regime_pass_gets_more_weight_but_never_dominates():
    ens = _ensemble()
    global_only = build_production_consensus(ens, _xgb([_forecast(10, 125.0)]), "TEST")
    regime = build_production_consensus(
        ens,
        _xgb([_forecast(10, 125.0, regime_gate="PASS", matching=3)]),
        "TEST",
    )
    assert regime.anchors[0].evidence_source == "global_plus_regime_pass"
    assert 0.20 <= regime.anchors[0].blend_weight <= 0.35
    assert regime.anchors[0].blend_weight > global_only.anchors[0].blend_weight
    assert regime.consensus[9] > global_only.consensus[9]
    assert regime.consensus[9] < 125.0


def test_only_passed_horizons_inside_daily_path_are_used():
    ens = _ensemble(10)
    forecasts = [
        _forecast(1, 102.0, regime_gate="PASS", matching=2),
        _forecast(5, 108.0),
        _forecast(10, 125.0, global_gate="HOLD"),
        _forecast(20, 150.0),
    ]
    result = build_production_consensus(ens, _xgb(forecasts), "TEST")
    assert result.used_horizons == [1, 5]
    assert len(result.anchors) == 2
    assert len(result.consensus) == 10
    assert np.all(np.isfinite(result.consensus))
