from __future__ import annotations

from market_forecaster.core.research_snapshots import (
    list_contract_snapshots,
    load_latest_contract,
    persist_forecast_contract,
)


def _contract(contract_id="abc123"):
    return {
        "schema_version": "4.0-forecast-contract-v1",
        "ticker": "AAPL",
        "generated_at": "2026-09-19T18:30:00+00:00",
        "contract_id": contract_id,
        "status": "READY",
        "forecasts": [{"horizon_days": 5}],
    }


def test_snapshot_persists_history_and_latest(tmp_path):
    paths = persist_forecast_contract(_contract(), repo_root=tmp_path)
    assert paths["history_path"]
    assert paths["latest_path"]
    latest = load_latest_contract("AAPL", repo_root=tmp_path)
    assert latest["contract_id"] == "abc123"


def test_snapshot_listing_excludes_latest_alias(tmp_path):
    persist_forecast_contract(_contract("one"), repo_root=tmp_path)
    second = _contract("two")
    second["generated_at"] = "2026-09-19T18:31:00+00:00"
    persist_forecast_contract(second, repo_root=tmp_path)
    rows = list_contract_snapshots("AAPL", repo_root=tmp_path, limit=10)
    assert len(rows) == 2
    assert {row["contract_id"] for row in rows} == {"one", "two"}
