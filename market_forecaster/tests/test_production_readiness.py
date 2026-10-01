from __future__ import annotations

import pytest

import market_forecaster.scripts.production_readiness as readiness


@pytest.fixture(autouse=True)
def _pro_api_services_ready(monkeypatch):
    monkeypatch.setattr(readiness, "api_key_store_status", lambda: (True, "ready"))
    monkeypatch.setattr(readiness, "api_usage_metering_status", lambda: (True, "ready"))


def test_readiness_passes_required_components_and_warns_on_disabled_billing(monkeypatch):
    monkeypatch.setattr(readiness, "MULTI_USER_ENABLED", True)
    monkeypatch.setattr(readiness, "DATABASE_PERSISTENCE_ENABLED", True)
    monkeypatch.setattr(readiness, "SHARED_CONTRACT_STORAGE_ENABLED", True)
    monkeypatch.setattr(readiness, "SHARED_AUTHORITY_ENABLED", True)
    monkeypatch.setattr(readiness, "SUBSCRIPTIONS_ENABLED", False)

    monkeypatch.setattr(readiness, "auth_configuration_status", lambda: (True, "ready"))
    monkeypatch.setattr(
        readiness,
        "browser_session_configuration_status",
        lambda: (True, "ready"),
    )
    monkeypatch.setattr(readiness, "persistence_configuration_status", lambda: (True, "ready"))
    monkeypatch.setattr(readiness, "shared_read_configuration_status", lambda: (True, "ready"))
    monkeypatch.setattr(
        readiness,
        "shared_authority_read_configuration_status",
        lambda: (True, "ready"),
    )
    monkeypatch.setattr(
        readiness,
        "subscription_configuration_status",
        lambda: (False, "SUBSCRIPTIONS_ENABLED is false."),
    )
    monkeypatch.setattr(
        readiness,
        "demo_cache_status",
        lambda: [
            {"ticker": f"T{i}", "available": True, "source": "shared_supabase"}
            for i in range(14)
        ],
    )

    class Settings:
        rate_limit_requests = 30
        rate_limit_window_seconds = 60
        shared_rate_limit_enabled = True

    monkeypatch.setattr(readiness, "load_settings", lambda: Settings())
    monkeypatch.setattr(
        readiness.SharedRateLimiter,
        "configured",
        lambda self: (True, "ready"),
    )

    report = readiness.evaluate_readiness()

    assert report["ready"] is True
    assert report["summary"]["fail"] == 0
    stripe = next(row for row in report["checks"] if row["name"] == "stripe_subscriptions")
    assert stripe["status"] == "WARN"


def test_readiness_can_require_billing(monkeypatch):
    monkeypatch.setattr(readiness, "MULTI_USER_ENABLED", False)
    monkeypatch.setattr(readiness, "DATABASE_PERSISTENCE_ENABLED", False)
    monkeypatch.setattr(readiness, "SHARED_CONTRACT_STORAGE_ENABLED", False)
    monkeypatch.setattr(readiness, "SHARED_AUTHORITY_ENABLED", False)
    monkeypatch.setattr(readiness, "SUBSCRIPTIONS_ENABLED", False)

    monkeypatch.setattr(readiness, "auth_configuration_status", lambda: (False, "disabled"))
    monkeypatch.setattr(
        readiness,
        "browser_session_configuration_status",
        lambda: (False, "disabled"),
    )
    monkeypatch.setattr(readiness, "persistence_configuration_status", lambda: (False, "disabled"))
    monkeypatch.setattr(readiness, "shared_read_configuration_status", lambda: (False, "disabled"))
    monkeypatch.setattr(
        readiness,
        "shared_authority_read_configuration_status",
        lambda: (False, "disabled"),
    )
    monkeypatch.setattr(
        readiness,
        "subscription_configuration_status",
        lambda: (False, "not configured"),
    )
    monkeypatch.setattr(
        readiness,
        "demo_cache_status",
        lambda: [
            {"ticker": f"T{i}", "available": True, "source": "local_cache"}
            for i in range(14)
        ],
    )

    class Settings:
        rate_limit_requests = 30
        rate_limit_window_seconds = 60
        shared_rate_limit_enabled = False

    monkeypatch.setattr(readiness, "load_settings", lambda: Settings())
    monkeypatch.setattr(
        readiness.SharedRateLimiter,
        "configured",
        lambda self: (False, "disabled"),
    )

    report = readiness.evaluate_readiness(require_billing=True)

    assert report["ready"] is False
    stripe = next(row for row in report["checks"] if row["name"] == "stripe_subscriptions")
    assert stripe["status"] == "FAIL"


def test_readiness_fails_when_demo_universe_is_incomplete(monkeypatch):
    monkeypatch.setattr(readiness, "MULTI_USER_ENABLED", False)
    monkeypatch.setattr(readiness, "DATABASE_PERSISTENCE_ENABLED", False)
    monkeypatch.setattr(readiness, "SHARED_CONTRACT_STORAGE_ENABLED", False)
    monkeypatch.setattr(readiness, "SHARED_AUTHORITY_ENABLED", False)
    monkeypatch.setattr(readiness, "SUBSCRIPTIONS_ENABLED", False)

    monkeypatch.setattr(readiness, "auth_configuration_status", lambda: (False, "disabled"))
    monkeypatch.setattr(readiness, "persistence_configuration_status", lambda: (False, "disabled"))
    monkeypatch.setattr(readiness, "shared_read_configuration_status", lambda: (False, "disabled"))
    monkeypatch.setattr(
        readiness,
        "shared_authority_read_configuration_status",
        lambda: (False, "disabled"),
    )
    monkeypatch.setattr(
        readiness,
        "subscription_configuration_status",
        lambda: (False, "disabled"),
    )
    monkeypatch.setattr(
        readiness,
        "demo_cache_status",
        lambda: [
            {"ticker": f"T{i}", "available": True, "source": "local_cache"}
            for i in range(13)
        ],
    )

    class Settings:
        rate_limit_requests = 30
        rate_limit_window_seconds = 60
        shared_rate_limit_enabled = False

    monkeypatch.setattr(readiness, "load_settings", lambda: Settings())
    monkeypatch.setattr(
        readiness.SharedRateLimiter,
        "configured",
        lambda self: (False, "disabled"),
    )

    report = readiness.evaluate_readiness()

    assert report["ready"] is False
    demo = next(row for row in report["checks"] if row["name"] == "demo_contracts")
    assert demo["status"] == "FAIL"



def test_readiness_requires_valid_stripe_catalog_when_billing_enabled(monkeypatch):
    monkeypatch.setattr(readiness, "MULTI_USER_ENABLED", False)
    monkeypatch.setattr(readiness, "DATABASE_PERSISTENCE_ENABLED", False)
    monkeypatch.setattr(readiness, "SHARED_CONTRACT_STORAGE_ENABLED", False)
    monkeypatch.setattr(readiness, "SHARED_AUTHORITY_ENABLED", False)
    monkeypatch.setattr(readiness, "SUBSCRIPTIONS_ENABLED", True)

    monkeypatch.setattr(readiness, "auth_configuration_status", lambda: (False, "disabled"))
    monkeypatch.setattr(
        readiness,
        "browser_session_configuration_status",
        lambda: (False, "disabled"),
    )
    monkeypatch.setattr(readiness, "persistence_configuration_status", lambda: (False, "disabled"))
    monkeypatch.setattr(readiness, "shared_read_configuration_status", lambda: (False, "disabled"))
    monkeypatch.setattr(
        readiness,
        "shared_authority_read_configuration_status",
        lambda: (False, "disabled"),
    )
    monkeypatch.setattr(
        readiness,
        "subscription_configuration_status",
        lambda: (True, "ready"),
    )
    monkeypatch.setattr(
        readiness,
        "stripe_catalog_status",
        lambda: (False, "Pro: price is inactive"),
    )
    monkeypatch.setattr(
        readiness,
        "demo_cache_status",
        lambda: [
            {"ticker": f"T{i}", "available": True, "source": "local_cache"}
            for i in range(14)
        ],
    )

    class Settings:
        rate_limit_requests = 30
        rate_limit_window_seconds = 60
        shared_rate_limit_enabled = False

    monkeypatch.setattr(readiness, "load_settings", lambda: Settings())
    monkeypatch.setattr(
        readiness.SharedRateLimiter,
        "configured",
        lambda self: (False, "disabled"),
    )

    report = readiness.evaluate_readiness()

    assert report["ready"] is False
    catalog = next(
        row for row in report["checks"] if row["name"] == "stripe_price_catalog"
    )
    assert catalog["status"] == "FAIL"
    assert "inactive" in catalog["detail"]


def test_readiness_requires_pro_api_key_store_for_paid_launch(monkeypatch):
    monkeypatch.setattr(readiness, "MULTI_USER_ENABLED", False)
    monkeypatch.setattr(readiness, "DATABASE_PERSISTENCE_ENABLED", False)
    monkeypatch.setattr(readiness, "SHARED_CONTRACT_STORAGE_ENABLED", False)
    monkeypatch.setattr(readiness, "SHARED_AUTHORITY_ENABLED", False)
    monkeypatch.setattr(readiness, "SUBSCRIPTIONS_ENABLED", True)

    monkeypatch.setattr(readiness, "auth_configuration_status", lambda: (False, "disabled"))
    monkeypatch.setattr(readiness, "browser_session_configuration_status", lambda: (False, "disabled"))
    monkeypatch.setattr(readiness, "persistence_configuration_status", lambda: (False, "disabled"))
    monkeypatch.setattr(readiness, "shared_read_configuration_status", lambda: (False, "disabled"))
    monkeypatch.setattr(
        readiness,
        "shared_authority_read_configuration_status",
        lambda: (False, "disabled"),
    )
    monkeypatch.setattr(readiness, "subscription_configuration_status", lambda: (True, "ready"))
    monkeypatch.setattr(readiness, "stripe_catalog_status", lambda: (True, "ready"))
    monkeypatch.setattr(readiness, "api_key_store_status", lambda: (False, "table missing"))
    monkeypatch.setattr(
        readiness,
        "demo_cache_status",
        lambda: [
            {"ticker": f"T{i}", "available": True, "source": "local_cache"}
            for i in range(14)
        ],
    )

    class Settings:
        rate_limit_requests = 30
        rate_limit_window_seconds = 60
        shared_rate_limit_enabled = False

    monkeypatch.setattr(readiness, "load_settings", lambda: Settings())
    monkeypatch.setattr(
        readiness.SharedRateLimiter,
        "configured",
        lambda self: (False, "disabled"),
    )

    report = readiness.evaluate_readiness()

    pro_api = next(
        row for row in report["checks"] if row["name"] == "pro_api_key_store"
    )
    assert pro_api["status"] == "FAIL"
    assert report["ready"] is False



def test_readiness_requires_pro_api_usage_metering_for_paid_launch(monkeypatch):
    monkeypatch.setattr(readiness, "MULTI_USER_ENABLED", False)
    monkeypatch.setattr(readiness, "DATABASE_PERSISTENCE_ENABLED", False)
    monkeypatch.setattr(readiness, "SHARED_CONTRACT_STORAGE_ENABLED", False)
    monkeypatch.setattr(readiness, "SHARED_AUTHORITY_ENABLED", False)
    monkeypatch.setattr(readiness, "SUBSCRIPTIONS_ENABLED", True)

    monkeypatch.setattr(readiness, "auth_configuration_status", lambda: (False, "disabled"))
    monkeypatch.setattr(
        readiness,
        "browser_session_configuration_status",
        lambda: (False, "disabled"),
    )
    monkeypatch.setattr(readiness, "persistence_configuration_status", lambda: (False, "disabled"))
    monkeypatch.setattr(readiness, "shared_read_configuration_status", lambda: (False, "disabled"))
    monkeypatch.setattr(
        readiness,
        "shared_authority_read_configuration_status",
        lambda: (False, "disabled"),
    )
    monkeypatch.setattr(readiness, "subscription_configuration_status", lambda: (True, "ready"))
    monkeypatch.setattr(readiness, "stripe_catalog_status", lambda: (True, "ready"))
    monkeypatch.setattr(readiness, "api_key_store_status", lambda: (True, "ready"))
    monkeypatch.setattr(
        readiness,
        "api_usage_metering_status",
        lambda: (False, "usage table missing"),
    )
    monkeypatch.setattr(
        readiness,
        "demo_cache_status",
        lambda: [
            {"ticker": f"T{i}", "available": True, "source": "local_cache"}
            for i in range(14)
        ],
    )

    class Settings:
        rate_limit_requests = 30
        rate_limit_window_seconds = 60
        shared_rate_limit_enabled = False

    monkeypatch.setattr(readiness, "load_settings", lambda: Settings())
    monkeypatch.setattr(
        readiness.SharedRateLimiter,
        "configured",
        lambda self: (False, "disabled"),
    )

    report = readiness.evaluate_readiness()

    metering = next(
        row for row in report["checks"] if row["name"] == "pro_api_usage_metering"
    )
    assert metering["status"] == "FAIL"
    assert "usage table missing" in metering["detail"]
    assert report["ready"] is False
