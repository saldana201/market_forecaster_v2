from __future__ import annotations

import json

import market_forecaster.services.shared_contract_store as shared_store
import market_forecaster.services.forecast_access as forecast_access


def _contract(ticker: str, generated_at: str, contract_id: str) -> dict:
    return {
        "ticker": ticker,
        "contract_id": contract_id,
        "generated_at": generated_at,
        "as_of": "2026-09-24",
        "status": "READY",
        "schema_version": "4.0-forecast-contract-v1",
        "forecasts": [],
    }


def test_shared_store_public_read_uses_publishable_key(monkeypatch):
    captured = {}

    monkeypatch.setenv("MARKET_FORECASTER_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("MARKET_FORECASTER_SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setattr(shared_store, "SHARED_CONTRACT_STORAGE_ENABLED", True)

    payload = [{
        "ticker": "SPY",
        "contract": _contract("SPY", "2026-09-24T18:00:00+00:00", "c1"),
    }]

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["apikey"] = req.headers["Apikey"]
        captured["authorization"] = req.headers.get("Authorization")
        return FakeResponse()

    monkeypatch.setattr(shared_store.request, "urlopen", fake_urlopen)

    rows = shared_store.load_shared_contracts(["SPY"])

    assert rows["SPY"]["contract_id"] == "c1"
    assert captured["apikey"] == "sb_publishable_test"
    assert captured["authorization"] is None
    assert "shared_forecast_contracts" in captured["url"]


def test_shared_store_publish_uses_service_role(monkeypatch):
    captured = {}

    monkeypatch.setenv("MARKET_FORECASTER_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("MARKET_FORECASTER_SUPABASE_SERVICE_ROLE_KEY", "service-role-test")
    monkeypatch.setattr(shared_store, "SHARED_CONTRACT_STORAGE_ENABLED", True)

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps([{
                "ticker": "SPY",
                "contract_id": "c2",
            }]).encode("utf-8")

    def fake_urlopen(req, timeout):
        captured["apikey"] = req.headers["Apikey"]
        captured["authorization"] = req.headers.get("Authorization")
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(shared_store.request, "urlopen", fake_urlopen)

    result = shared_store.publish_shared_contract(
        _contract("SPY", "2026-09-24T19:00:00+00:00", "c2")
    )

    assert result["contract_id"] == "c2"
    assert captured["apikey"] == "service-role-test"
    assert captured["authorization"] == "Bearer service-role-test"
    assert captured["body"]["ticker"] == "SPY"


def test_forecast_access_prefers_freshest_contract(monkeypatch):
    older = _contract("SPY", "2026-09-24T18:00:00+00:00", "old")
    newer = _contract("SPY", "2026-09-24T19:00:00+00:00", "new")

    monkeypatch.setattr(forecast_access, "SHARED_CONTRACT_STORAGE_ENABLED", True)
    monkeypatch.setattr(forecast_access, "load_latest_contract", lambda *args, **kwargs: older)
    monkeypatch.setattr(forecast_access, "load_shared_contract", lambda *args, **kwargs: newer)

    contract, source = forecast_access._load_best_contract("SPY")

    assert contract["contract_id"] == "new"
    assert source == "shared_supabase"


def test_forecast_access_falls_back_to_local_on_shared_error(monkeypatch):
    local = _contract("SPY", "2026-09-24T19:00:00+00:00", "local")

    monkeypatch.setattr(forecast_access, "SHARED_CONTRACT_STORAGE_ENABLED", True)
    monkeypatch.setattr(forecast_access, "load_latest_contract", lambda *args, **kwargs: local)

    def fail(*args, **kwargs):
        raise forecast_access.SharedContractStoreError("temporary outage")

    monkeypatch.setattr(forecast_access, "load_shared_contract", fail)

    contract, source = forecast_access._load_best_contract("SPY")

    assert contract["contract_id"] == "local"
    assert source == "local_cache"
