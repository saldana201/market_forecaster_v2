from __future__ import annotations

from market_forecaster.ui.forecast_dashboard import (
    evidence_quality,
    expected_range,
    outlook_label,
    plain_language_summary,
    primary_forecast,
)


def _row(horizon=10, expected=2.5, probability=63.0, status="CALIBRATED", samples=100):
    return {
        "horizon_days": horizon,
        "expected_return_pct": expected,
        "probability_up_pct": probability,
        "projected_price": 102.5,
        "price_range_80": [95.0, 108.0],
        "price_range_90": [92.0, 111.0],
        "calibration_status": status,
        "calibration_samples": samples,
        "diagnostics": {
            "brier_score": 0.22,
            "coverage_80_pct": 81.0,
            "coverage_90_pct": 90.0,
        },
    }


def test_primary_forecast_prefers_10_day_for_plain_language_anchor():
    rows = [_row(1), _row(5), _row(20), _row(10)]
    assert primary_forecast(rows)["horizon_days"] == 10


def test_evidence_quality_translates_good_calibration_to_strong():
    assert evidence_quality(_row()) == "Strong"


def test_evidence_quality_marks_small_sample_limited():
    assert evidence_quality(_row(status="PROVISIONAL", samples=12)) == "Limited"


def test_expected_range_is_plain_language_money_range():
    assert expected_range(_row(), 80) == "$95.00 – $108.00"


def test_outlook_label_uses_neutral_band_around_zero():
    assert outlook_label(0.2) == "mixed"
    assert outlook_label(1.5) == "slightly positive"
    assert outlook_label(-1.5) == "slightly negative"


def test_summary_uses_plain_language_not_research_jargon():
    contract = {
        "forecasts": [
            _row(10, expected=3.2, probability=64.0),
            {**_row(20, expected=4.0, probability=66.0), "price_range_80": [88.0, 116.0]},
        ]
    }
    text = plain_language_summary(contract)
    assert "10-day outlook is positive" in text
    assert "64%" in text
    assert "OOS" not in text
    assert "Brier" not in text
