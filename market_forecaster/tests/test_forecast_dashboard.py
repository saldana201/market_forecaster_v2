from __future__ import annotations

from market_forecaster.ui.forecast_dashboard import (
    _forecast_contract_json,
    _forecast_export_filename,
    _forecast_export_frame,
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



def test_forecast_export_frame_flattens_canonical_horizons():
    contract = {
        "ticker": "aapl",
        "contract_id": "contract-123",
        "generated_at": "2026-09-27T20:00:00Z",
        "as_of": "2026-09-27",
        "current_price": 100.0,
        "forecasts": [
            {
                **_row(5, expected=1.2, probability=58.0),
                "model": "ridge",
                "calibration_status": "CALIBRATED",
            },
            {
                **_row(1, expected=0.4, probability=54.0),
                "model": "prophet",
                "calibration_status": "CALIBRATED",
            },
        ],
    }

    frame = _forecast_export_frame(contract)

    assert list(frame["horizon_days"]) == [1, 5]
    assert list(frame["ticker"]) == ["AAPL", "AAPL"]
    assert frame.iloc[0]["contract_id"] == "contract-123"
    assert frame.iloc[0]["current_price"] == 100.0
    assert frame.iloc[0]["price_range_80_low"] == 95.0
    assert frame.iloc[0]["price_range_80_high"] == 108.0
    assert frame.iloc[0]["evidence"] == "Strong"


def test_forecast_export_filename_is_ticker_and_date_scoped():
    contract = {
        "ticker": "msft",
        "generated_at": "2026-09-27T20:00:00Z",
    }

    assert (
        _forecast_export_filename(contract, "csv")
        == "MSFT_forecast_contract_2026-09-27.csv"
    )


def test_forecast_contract_json_preserves_full_contract():
    contract = {
        "ticker": "SPY",
        "contract_id": "contract-xyz",
        "forecasts": [{"horizon_days": 10, "diagnostics": {"brier_score": 0.21}}],
        "data_quality": {"provider": "yfinance"},
    }

    exported = _forecast_contract_json(contract)

    assert '"contract_id": "contract-xyz"' in exported
    assert '"brier_score": 0.21' in exported
    assert '"provider": "yfinance"' in exported
