from __future__ import annotations

import market_forecaster.scripts.production_readiness as readiness


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
