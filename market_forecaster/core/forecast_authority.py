"""Horizon-specific Forecast Authority registry for Market Forecaster 4.0.

The registry is explicit and manual by design. Research results can inform a
human decision to change the authority, but a single experiment never promotes
it automatically.
"""
from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path

from market_forecaster.config import SHARED_AUTHORITY_ENABLED
from market_forecaster.core.model_tournament import (
    is_model_available,
    model_status_map,
)
from market_forecaster.core.market_context import ALL_CONTEXT_FAMILIES
from market_forecaster.core.targets import DEFAULT_RESEARCH_HORIZONS
from market_forecaster.services.shared_authority_store import (
    SharedAuthorityStoreError,
    load_shared_authority,
    publish_shared_authority,
    shared_authority_write_configuration_status,
)

AUTHORITY_SCHEMA_VERSION = "4.0-authority-v1"
AUTHORITY_FILENAME = "forecast_authority.json"

_DEFAULT_ROW = {
    "model": "xgboost",
    "context_family": "none",
    "sector_ticker": None,
    "calibration_window": 120,
    "enabled": True,
}


def default_authority_config() -> dict:
    return {
        "schema_version": AUTHORITY_SCHEMA_VERSION,
        "horizons": {
            str(int(h)): deepcopy(_DEFAULT_ROW)
            for h in DEFAULT_RESEARCH_HORIZONS
        },
        "notes": [
            "Authority changes are explicit; research runs do not auto-promote models or feature families.",
            "Trading/execution decisions are outside this registry.",
        ],
    }


def authority_path(repo_root: str | Path | None = None) -> Path:
    if repo_root is not None:
        root = Path(repo_root)
    else:
        env_root = os.getenv("MARKET_FORECASTER_REPO_ROOT", "").strip()
        root = Path(env_root) if env_root else Path.cwd()
    return root / ".local" / AUTHORITY_FILENAME


def _normalize_row(row: dict, horizon: int) -> dict:
    model = str(row.get("model", "xgboost")).strip().lower()
    context = str(row.get("context_family", "none")).strip().lower()
    sector = row.get("sector_ticker")
    sector = str(sector).upper().strip() if sector else None
    window = row.get("calibration_window", 120)
    window = None if window in (None, 0, "0", "all", "ALL") else int(window)
    return {
        "model": model,
        "context_family": context,
        "sector_ticker": sector,
        "calibration_window": window,
        "enabled": bool(row.get("enabled", True)),
        "horizon": int(horizon),
    }


def validate_authority_config(config: dict, *, require_available_models: bool = True) -> dict:
    errors = []
    normalized = {
        "schema_version": AUTHORITY_SCHEMA_VERSION,
        "horizons": {},
        "notes": list(config.get("notes", [])) if isinstance(config, dict) else [],
    }

    horizons = config.get("horizons", {}) if isinstance(config, dict) else {}
    registry = model_status_map()

    for horizon in DEFAULT_RESEARCH_HORIZONS:
        raw = horizons.get(str(horizon), horizons.get(horizon, deepcopy(_DEFAULT_ROW)))
        try:
            row = _normalize_row(raw or {}, horizon)
        except Exception as exc:
            errors.append(f"{horizon}D: invalid row: {exc}")
            continue

        model = row["model"]
        context = row["context_family"]

        if model not in registry:
            errors.append(f"{horizon}D: unknown model '{model}'")
        elif model in {"zero_return", "historical_mean"}:
            errors.append(f"{horizon}D: baselines cannot be Forecast Authority models")
        elif require_available_models and not is_model_available(model):
            errors.append(f"{horizon}D: model '{model}' is not installed/available")

        if context != "none" and context not in ALL_CONTEXT_FAMILIES:
            errors.append(f"{horizon}D: unknown context family '{context}'")

        if context == "sector" and not row["sector_ticker"]:
            errors.append(f"{horizon}D: sector context requires sector_ticker")

        if row["calibration_window"] is not None and row["calibration_window"] < 40:
            errors.append(f"{horizon}D: calibration_window must be >=40 or all history")

        normalized["horizons"][str(horizon)] = {
            k: v for k, v in row.items() if k != "horizon"
        }

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "config": normalized,
    }


def _load_local_authority(repo_root: str | Path | None = None) -> dict:
    path = authority_path(repo_root)
    if not path.exists():
        return default_authority_config()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default_authority_config()


def load_authority_config(
    *,
    repo_root: str | Path | None = None,
    require_available_models: bool = False,
) -> dict:
    shared_warning = None

    # Explicit repo_root calls are intentionally local-only for tests/offline
    # research. Production calls use the shared authority first when enabled.
    if repo_root is None and SHARED_AUTHORITY_ENABLED:
        try:
            shared_config = load_shared_authority()
            if isinstance(shared_config, dict):
                shared_check = validate_authority_config(
                    shared_config,
                    require_available_models=require_available_models,
                )
                if shared_check["status"] == "PASS":
                    return shared_check["config"]
                shared_warning = (
                    "Invalid shared Forecast Authority: "
                    + "; ".join(shared_check["errors"])
                )
            else:
                shared_warning = "Shared Forecast Authority row is missing."
        except SharedAuthorityStoreError as exc:
            shared_warning = str(exc)

    local_config = _load_local_authority(repo_root)
    local_check = validate_authority_config(
        local_config,
        require_available_models=require_available_models,
    )
    if local_check["status"] == "FAIL":
        # Invalid local fallback must never silently become active.
        fallback = default_authority_config()
        warnings = list(local_check["errors"])
        if shared_warning:
            warnings.insert(0, shared_warning)
        fallback["load_warning"] = "; ".join(warnings)
        return fallback

    result = local_check["config"]
    if shared_warning:
        result["load_warning"] = (
            "Shared Forecast Authority unavailable; local fallback is active: "
            + shared_warning
        )
    return result


def save_authority_config(
    config: dict,
    *,
    repo_root: str | Path | None = None,
) -> dict:
    check = validate_authority_config(config, require_available_models=True)
    if check["status"] != "PASS":
        raise ValueError("Invalid Forecast Authority: " + "; ".join(check["errors"]))

    payload = check["config"]

    # In production, a global authority change must be published through a
    # trusted service-role context. Never let one Azure instance silently write
    # a local-only authority that other instances cannot see.
    if repo_root is None and SHARED_AUTHORITY_ENABLED:
        write_ready, reason = shared_authority_write_configuration_status()
        if not write_ready:
            raise PermissionError(
                "Shared Forecast Authority is read-only in this runtime. "
                + reason
            )
        publish_shared_authority(payload)

    path = authority_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(
        prefix="forecast_authority_",
        suffix=".json.tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)

    return payload


def authority_rows(config: dict | None = None) -> list[dict]:
    cfg = config or load_authority_config()
    rows = []
    for horizon in DEFAULT_RESEARCH_HORIZONS:
        row = dict(cfg.get("horizons", {}).get(str(horizon), _DEFAULT_ROW))
        row["horizon"] = int(horizon)
        rows.append(row)
    return rows
