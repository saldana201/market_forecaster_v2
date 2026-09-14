from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from market_forecaster.core.options_promotion import (
    OptionsPromotionAnchor,
    OptionsPromotionResult,
    build_adaptive_options_consensus,
    promotion_gate_for_horizon,
    promotion_weight,
)


def _validation(*, latest_win=True, gate="PASS"):
    return {
        "horizon": 5,
        "gate": gate,
        "improvement_pct": 12.0,
        "directional_accuracy": 61.0,
        "fold_win_rate": 2 / 3,
        "fold_metrics": [
            {"fold": 1, "model_mae": 0.010, "baseline_mae": 0.012, "beat_baseline": True},
            {"fold": 2, "model_mae": 0.011, "baseline_mae": 0.012, "beat_baseline": True},
            {
                "fold": 3,
                "model_mae": 0.010 if latest_win else 0.014,
                "baseline_mae": 0.012,
                "beat_baseline": latest_win,
            },
        ],
    }


def _base():
    dates = pd.bdate_range("2026-01-05", periods=20)
    base = np.linspace(100.0, 110.0, 20)
    return SimpleNamespace(
        ticker="TEST",
        dates=dates,
        ensemble=base.copy(),
        consensus=base.copy(),
        lower=base * 0.95,
        upper=base * 1.05,
        anchors=[],
        current_regime="RANGE",
        status="ENSEMBLE_ONLY",
    )


def test_latest_oos_loss_auto_demotes():
    ok, reason = promotion_gate_for_horizon(
        _validation(latest_win=False),
        current_feature_completeness=0.9,
    )
    assert not ok
    assert reason == "latest_oos_fold_demoted"


def test_incomplete_current_snapshot_holds():
    ok, reason = promotion_gate_for_horizon(
        _validation(latest_win=True),
        current_feature_completeness=0.4,
    )
    assert not ok
    assert reason == "current_feature_coverage_hold"


def test_options_weight_is_hard_capped():
    w = promotion_weight({
        "gate": "PASS",
        "improvement_pct": 1000,
        "directional_accuracy": 100,
        "fold_win_rate": 1.0,
    })
    assert 0.05 <= w <= 0.15


def test_no_active_anchor_leaves_base_consensus_unchanged():
    base = _base()
    promotion = OptionsPromotionResult(
        ticker="TEST", as_of_utc="", spot=100.0,
        status="HOLD", validation_status="READY",
        unique_sessions=100, anchors=[], promoted_horizons=[],
        notes=[],
    )
    result = build_adaptive_options_consensus(base, promotion)
    assert np.allclose(result.consensus, base.consensus)
    assert result.status == "ENSEMBLE_ONLY"


def test_active_options_anchor_adjusts_but_does_not_replace_path():
    base = _base()
    anchor = OptionsPromotionAnchor(
        horizon=5,
        predicted_return=0.10,
        target_price=110.0,
        blend_weight=0.15,
        feature_completeness=1.0,
        global_gate="PASS",
        recent_fold_gate="PASS",
        improvement_pct=12.0,
        directional_accuracy_pct=61.0,
        fold_win_rate=2/3,
        training_samples=80,
        empirical_floor=-0.20,
        empirical_ceiling=0.20,
    )
    promotion = OptionsPromotionResult(
        ticker="TEST", as_of_utc="", spot=100.0,
        status="ACTIVE", validation_status="READY",
        unique_sessions=100, anchors=[anchor], promoted_horizons=[5],
        notes=[],
    )
    result = build_adaptive_options_consensus(base, promotion)
    assert result.status == "OPTIONS_ADAPTIVE_CONSENSUS"
    assert len(result.options_anchors) == 1
    assert not np.allclose(result.consensus, base.consensus)
    # A 15% evidence weight must not simply replace the base 5D point with 110.
    assert result.consensus[4] < 110.0
    assert result.consensus[4] > base.consensus[4]
