from __future__ import annotations

import json

from market_forecaster.scripts.check_demo_cache import summarize_demo_cache
from market_forecaster.services.forecast_access import demo_cache_status


def test_demo_cache_status_reports_each_registered_symbol(tmp_path):
    rows = demo_cache_status(repo_root=tmp_path)
    assert len(rows) == 14
    assert not any(row["available"] for row in rows)


def test_demo_cache_summary_identifies_ready_and_missing_symbols(tmp_path):
    root = tmp_path / ".local" / "forecast_contracts" / "SPY"
    root.mkdir(parents=True)
    (root / "latest.json").write_text(
        json.dumps(
            {
                "ticker": "SPY",
                "contract_id": "spy-ready",
                "generated_at": "2026-09-21T21:00:00+00:00",
                "as_of": "2026-09-21",
                "current_price": 650.0,
                "forecasts": [],
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_demo_cache(repo_root=tmp_path)
    assert summary["ready"] == 1
    assert summary["total"] == 14
    assert summary["complete"] is False
    assert summary["ready_tickers"] == ["SPY"]
    assert "AAPL" in summary["missing_tickers"]
