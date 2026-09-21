from __future__ import annotations

from fastapi.testclient import TestClient

from market_forecaster.api.main import app


client = TestClient(app)


def test_public_demo_universe_does_not_require_api_key():
    response = client.get("/api/v1/public/demo-universe")
    assert response.status_code == 200
    body = response.json()
    assert len(body["symbols"]) == 14
    assert any(row["ticker"] == "AAPL" for row in body["symbols"])


def test_public_demo_forecast_rejects_non_demo_ticker_without_training():
    response = client.get("/api/v1/public/forecast-contract/NVDA")
    assert response.status_code == 403
