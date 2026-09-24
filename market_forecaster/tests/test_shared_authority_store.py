from __future__ import annotations

import json

import market_forecaster.services.shared_authority_store as authority_store


def _config() -> dict:
    return {
        "schema_version": "4.0-authority-v1",
        "horizons": {
            "1": {"model": "xgboost", "context_family": "none", "sector_ticker": None, "calibration_window": 120, "enabled": True},
            "5": {"model": "xgboost", "context_family": "none", "sector_ticker": None, "calibration_window": 120, "enabled": True},
            "10": {"model": "xgboost", "context_family": "none", "sector_ticker": None, "calibration_window": 120, "enabled": True},
            "20": {"model": "xgboost", "context_family": "none", "sector_ticker": None, "calibration_window": 120, "enabled": True},
        },
        "notes": [],
    }


def test_shared_authority_read_uses_publishable_key(monkeypatch):
    captured = {}

    monkeypatch.setenv("MARKET_FORECASTER_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("MARKET_FORECASTER_SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setattr(authority_store, "SHARED_AUTHORITY_ENABLED", True)

    payload = [{"config": _config(), "revision": 1, "updated_at": "2026-09-24T00:00:00Z"}]

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    def fake_urlopen(req, timeout):
        captured["apikey"] = req.headers["Apikey"]
        captured["authorization"] = req.headers.get("Authorization")
        captured["url"] = req.full_url
        return FakeResponse()

    monkeypatch.setattr(authority_store.request, "urlopen", fake_urlopen)

    result = authority_store.load_shared_authority()

    assert result == _config()
    assert captured["apikey"] == "sb_publishable_test"
    assert captured["authorization"] is None
    assert "authority_key=eq.active" in captured["url"]


def test_shared_authority_publish_requires_service_role(monkeypatch):
    monkeypatch.setenv("MARKET_FORECASTER_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.delenv("MARKET_FORECASTER_SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setattr(authority_store, "SHARED_AUTHORITY_ENABLED", True)

    ready, reason = authority_store.shared_authority_write_configuration_status()

    assert ready is False
    assert "service-role" in reason


def test_shared_authority_publish_uses_service_role(monkeypatch):
    calls = []

    monkeypatch.setenv("MARKET_FORECASTER_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("MARKET_FORECASTER_SUPABASE_SERVICE_ROLE_KEY", "service-role-test")
    monkeypatch.setattr(authority_store, "SHARED_AUTHORITY_ENABLED", True)

    responses = [
        [{"revision": 2}],
        [{"authority_key": "active", "revision": 3}],
    ]

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(req, timeout):
        calls.append({
            "method": req.method,
            "authorization": req.headers.get("Authorization"),
            "body": json.loads(req.data.decode("utf-8")) if req.data else None,
        })
        return FakeResponse(responses[len(calls) - 1])

    monkeypatch.setattr(authority_store.request, "urlopen", fake_urlopen)

    result = authority_store.publish_shared_authority(_config())

    assert result["revision"] == 3
    assert all(call["authorization"] == "Bearer service-role-test" for call in calls)
    assert calls[1]["body"]["revision"] == 3
    assert calls[1]["body"]["config"] == _config()
