from datetime import datetime, timezone
import pandas as pd
from market_forecaster.core import operations

NOW = datetime(2026, 9, 14, 18, 0, tzinfo=timezone.utc)


def _stock(date="2026-09-14"):
    df = pd.DataFrame({"Date": [pd.Timestamp(date)], "Open": [100.0], "Close": [101.0]})
    df.attrs["provider"] = "test-provider"
    return df


def _patch_dependencies(monkeypatch):
    monkeypatch.setattr(operations, "audit_snapshot", lambda *a, **k: {
        "runs": 1, "targets": 4, "resolved_targets": 0, "pending_targets": 4
    })
    monkeypatch.setattr(operations, "deployment_policy_state", lambda *a, **k: {
        "approved_champion": "adaptive_production_consensus",
        "effective_champion": "adaptive_production_consensus",
        "policy_status": "DEFAULT_INCUMBENT",
        "approved_drift": {"status": "HEALTHY"},
        "incumbent_drift": {"status": "HEALTHY"},
        "governance": {"recommendation": "COLLECT_MORE_REALIZED_OUTCOMES"},
    })


def test_event_log_round_trip(tmp_path):
    operations.record_operation_event("SPY", "ensemble", "ERROR", "boom",
                                      base_dir=tmp_path, now=NOW)
    rows = operations.load_operation_events("SPY", base_dir=tmp_path)
    assert len(rows) == 1 and rows[0]["status"] == "ERROR"


def test_equity_freshness_uses_business_days():
    r = operations.assess_data_freshness("SPY", _stock("2026-09-11"), now=NOW)
    assert r["age_unit"] == "business_days" and r["age"] == 1 and r["status"] == "OK"


def test_crypto_freshness_uses_calendar_days():
    r = operations.assess_data_freshness("ETH-USD", _stock("2026-09-11"), now=NOW)
    assert r["age_unit"] == "calendar_days" and r["age"] == 3 and r["status"] == "STALE"


def test_cycle_respects_cadence(tmp_path, monkeypatch):
    _patch_dependencies(monkeypatch)
    monkeypatch.setattr(operations, "reconcile_matured_outcomes",
                        lambda *a, **k: {"created": 1, "matured": 1, "pending": 2})
    first = operations.run_operations_cycle("SPY", _stock(), base_dir=tmp_path, now=NOW)
    second = operations.run_operations_cycle(
        "SPY", _stock(), base_dir=tmp_path,
        now=datetime(2026, 9, 14, 18, 10, tzinfo=timezone.utc),
    )
    assert first["cycle_status"] == "SUCCESS"
    assert second["cycle_status"] == "SKIPPED_CADENCE"


def test_health_surfaces_recent_forecast_failures(tmp_path, monkeypatch):
    _patch_dependencies(monkeypatch)
    operations.record_operation_event("SPY", "ensemble", "ERROR", "failure",
                                      base_dir=tmp_path, now=NOW)
    r = operations.operations_health("SPY", _stock(), base_dir=tmp_path, now=NOW)
    assert r["forecast_status"] == "WATCH" and r["errors_24h"] == 1


def test_health_degrades_for_stale_market_data(tmp_path, monkeypatch):
    _patch_dependencies(monkeypatch)
    r = operations.operations_health("SPY", _stock("2026-09-08"),
                                     base_dir=tmp_path, now=NOW)
    assert r["provider_status"] == "DEGRADED"
    assert r["overall_status"] == "DEGRADED"
