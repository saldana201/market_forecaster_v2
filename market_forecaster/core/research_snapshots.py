"""Atomic research snapshot storage for Forecast Contracts."""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_SAFE = re.compile(r"[^A-Z0-9._-]+")


def _safe_ticker(ticker: str) -> str:
    value = _SAFE.sub("_", str(ticker or "").upper().strip())
    return value or "UNKNOWN"


def snapshot_root(repo_root: str | Path | None = None) -> Path:
    if repo_root is not None:
        root = Path(repo_root)
    else:
        env_root = os.getenv("MARKET_FORECASTER_REPO_ROOT", "").strip()
        root = Path(env_root) if env_root else Path.cwd()
    return root / ".local" / "forecast_contracts"


def _atomic_json_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=path.stem + "_",
        suffix=".json.tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def persist_forecast_contract(
    contract: dict,
    *,
    repo_root: str | Path | None = None,
) -> dict:
    ticker = _safe_ticker(contract.get("ticker", "UNKNOWN"))
    root = snapshot_root(repo_root) / ticker
    generated = str(contract.get("generated_at") or datetime.now(timezone.utc).isoformat())
    stamp = re.sub(r"[^0-9]", "", generated)[:20] or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    contract_id = str(contract.get("contract_id", "noid"))[:16]
    filename = f"{stamp}_{contract_id}.json"

    history_path = root / filename
    latest_path = root / "latest.json"
    _atomic_json_write(history_path, contract)
    _atomic_json_write(latest_path, contract)

    return {
        "history_path": str(history_path),
        "latest_path": str(latest_path),
    }


def load_latest_contract(
    ticker: str,
    *,
    repo_root: str | Path | None = None,
) -> dict | None:
    path = snapshot_root(repo_root) / _safe_ticker(ticker) / "latest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_contract_snapshots(
    ticker: str,
    *,
    repo_root: str | Path | None = None,
    limit: int = 20,
) -> list[dict]:
    root = snapshot_root(repo_root) / _safe_ticker(ticker)
    if not root.exists():
        return []

    files = sorted(
        [p for p in root.glob("*.json") if p.name != "latest.json"],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[: max(1, int(limit))]

    rows = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows.append({
                "filename": path.name,
                "generated_at": payload.get("generated_at"),
                "contract_id": payload.get("contract_id"),
                "status": payload.get("status"),
                "ticker": payload.get("ticker"),
                "horizons": len(payload.get("forecasts", [])),
            })
        except Exception:
            continue
    return rows
