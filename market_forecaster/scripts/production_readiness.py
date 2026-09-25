"""Production-readiness gate for Market Forecaster 4.1.x."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass

from market_forecaster.api.settings import load_settings
from market_forecaster.api.shared_rate_limit import SharedRateLimiter
from market_forecaster.auth.factory import auth_configuration_status
from market_forecaster.config import (
    DATABASE_PERSISTENCE_ENABLED,
    MULTI_USER_ENABLED,
    SHARED_AUTHORITY_ENABLED,
    SHARED_CONTRACT_STORAGE_ENABLED,
    SUBSCRIPTIONS_ENABLED,
    __version__,
)
from market_forecaster.services.forecast_access import demo_cache_status
from market_forecaster.services.shared_authority_store import (
    shared_authority_read_configuration_status,
)
from market_forecaster.services.shared_contract_store import (
    shared_read_configuration_status,
)
from market_forecaster.services.subscriptions import subscription_configuration_status
from market_forecaster.services.user_data import persistence_configuration_status


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    status: str
    required: bool
    detail: str


def _check(name: str, ready: bool, required: bool, detail: str) -> ReadinessCheck:
    if ready:
        status = "PASS"
    elif required:
        status = "FAIL"
    else:
        status = "WARN"
    return ReadinessCheck(name=name, status=status, required=required, detail=detail)


def evaluate_readiness(*, require_billing: bool = False) -> dict:
    checks: list[ReadinessCheck] = []

    auth_ready, auth_reason = auth_configuration_status()
    checks.append(
        _check(
            "managed_authentication",
            auth_ready,
            MULTI_USER_ENABLED,
            "ready" if auth_ready else auth_reason,
        )
    )

    persistence_ready, persistence_reason = persistence_configuration_status()
    checks.append(
        _check(
            "persistent_user_data",
            persistence_ready,
            DATABASE_PERSISTENCE_ENABLED,
            "ready" if persistence_ready else persistence_reason,
        )
    )

    shared_ready, shared_reason = shared_read_configuration_status()
    checks.append(
        _check(
            "shared_forecast_contract_storage",
            shared_ready,
            SHARED_CONTRACT_STORAGE_ENABLED,
            "ready" if shared_ready else shared_reason,
        )
    )

    authority_ready, authority_reason = shared_authority_read_configuration_status()
    checks.append(
        _check(
            "shared_forecast_authority",
            authority_ready,
            SHARED_AUTHORITY_ENABLED,
            "ready" if authority_ready else authority_reason,
        )
    )

    try:
        demo_rows = demo_cache_status()
        demo_ready = len(demo_rows) == 14 and all(
            row.get("available") for row in demo_rows
        )
        shared_count = sum(
            1 for row in demo_rows if row.get("source") == "shared_supabase"
        )
        demo_detail = (
            f"{len([row for row in demo_rows if row.get('available')])}/14 available; "
            f"{shared_count}/14 served from shared storage"
        )
    except Exception as exc:
        demo_ready = False
        demo_detail = f"Demo cache check failed: {type(exc).__name__}"
    checks.append(
        _check(
            "demo_contracts",
            demo_ready,
            True,
            demo_detail,
        )
    )

    billing_ready, billing_reason = subscription_configuration_status()
    checks.append(
        _check(
            "stripe_subscriptions",
            billing_ready,
            require_billing or SUBSCRIPTIONS_ENABLED,
            "ready" if billing_ready else billing_reason,
        )
    )

    try:
        api_settings = load_settings()
        limiter = SharedRateLimiter(
            requests=api_settings.rate_limit_requests,
            window_seconds=api_settings.rate_limit_window_seconds,
            enabled=api_settings.shared_rate_limit_enabled,
        )
        limiter_ready, limiter_reason = limiter.configured()
        limiter_required = api_settings.shared_rate_limit_enabled
        limiter_detail = "ready" if limiter_ready else limiter_reason
    except Exception as exc:
        limiter_ready = False
        limiter_required = True
        limiter_detail = f"API settings check failed: {type(exc).__name__}"

    checks.append(
        _check(
            "shared_api_rate_limit",
            limiter_ready,
            limiter_required,
            limiter_detail,
        )
    )

    failed = [row for row in checks if row.status == "FAIL"]
    warnings = [row for row in checks if row.status == "WARN"]

    return {
        "version": __version__,
        "ready": not failed,
        "strict_billing": bool(require_billing),
        "summary": {
            "pass": len([row for row in checks if row.status == "PASS"]),
            "warn": len(warnings),
            "fail": len(failed),
        },
        "checks": [asdict(row) for row in checks],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate Market Forecaster production readiness without exposing secrets."
    )
    parser.add_argument(
        "--require-billing",
        action="store_true",
        help="Treat disabled/unconfigured Stripe subscriptions as a release-blocking failure.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any required readiness check fails.",
    )
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    report = evaluate_readiness(require_billing=args.require_billing)
    print(json.dumps(report, indent=None if args.compact else 2, default=str))

    if args.strict and not report["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
