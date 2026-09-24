from __future__ import annotations

from market_forecaster.core.forecast_authority import (
    default_authority_config,
    load_authority_config,
    save_authority_config,
    validate_authority_config,
)


def test_default_authority_covers_four_canonical_horizons():
    config = default_authority_config()
    assert set(config["horizons"]) == {"1", "5", "10", "20"}
    assert all(row["model"] == "xgboost" for row in config["horizons"].values())
    assert all(row["context_family"] == "none" for row in config["horizons"].values())


def test_authority_rejects_baseline_model():
    config = default_authority_config()
    config["horizons"]["5"]["model"] = "zero_return"
    check = validate_authority_config(config, require_available_models=False)
    assert check["status"] == "FAIL"
    assert any("baselines" in error.lower() for error in check["errors"])


def test_sector_context_requires_sector_ticker():
    config = default_authority_config()
    config["horizons"]["10"]["context_family"] = "sector"
    config["horizons"]["10"]["sector_ticker"] = None
    check = validate_authority_config(config, require_available_models=False)
    assert check["status"] == "FAIL"
    assert any("sector_ticker" in error for error in check["errors"])


def test_authority_save_load_roundtrip(tmp_path):
    config = default_authority_config()
    config["horizons"]["20"]["calibration_window"] = 250
    saved = save_authority_config(config, repo_root=tmp_path)
    loaded = load_authority_config(repo_root=tmp_path, require_available_models=True)
    assert saved == loaded
    assert loaded["horizons"]["20"]["calibration_window"] == 250



def test_shared_authority_is_preferred_when_enabled(monkeypatch):
    import market_forecaster.core.forecast_authority as authority

    shared = default_authority_config()
    shared["horizons"]["20"]["calibration_window"] = 250

    monkeypatch.setattr(authority, "SHARED_AUTHORITY_ENABLED", True)
    monkeypatch.setattr(authority, "load_shared_authority", lambda: shared)

    loaded = load_authority_config(require_available_models=False)

    assert loaded["horizons"]["20"]["calibration_window"] == 250
    assert "load_warning" not in loaded


def test_invalid_shared_authority_falls_back_to_local(monkeypatch, tmp_path):
    import market_forecaster.core.forecast_authority as authority

    local = default_authority_config()
    local["horizons"]["20"]["calibration_window"] = 250
    local_path = tmp_path / ".local" / "forecast_authority.json"
    local_path.parent.mkdir(parents=True, exist_ok=True)
    import json
    local_path.write_text(json.dumps(local), encoding="utf-8")

    invalid_shared = default_authority_config()
    invalid_shared["horizons"]["5"]["model"] = "zero_return"

    monkeypatch.setattr(authority, "SHARED_AUTHORITY_ENABLED", True)
    monkeypatch.setattr(authority, "load_shared_authority", lambda: invalid_shared)
    monkeypatch.setattr(authority, "authority_path", lambda repo_root=None: local_path)

    loaded = load_authority_config(require_available_models=False)

    assert loaded["horizons"]["20"]["calibration_window"] == 250
    assert "local fallback is active" in loaded["load_warning"]


def test_shared_authority_save_requires_trusted_writer(monkeypatch):
    import market_forecaster.core.forecast_authority as authority

    monkeypatch.setattr(authority, "SHARED_AUTHORITY_ENABLED", True)
    monkeypatch.setattr(
        authority,
        "shared_authority_write_configuration_status",
        lambda: (False, "Trusted Supabase service-role credential is not configured."),
    )

    try:
        save_authority_config(default_authority_config())
        assert False, "Expected PermissionError"
    except PermissionError as exc:
        assert "read-only" in str(exc)


def test_shared_authority_save_publishes_before_local_write(monkeypatch, tmp_path):
    import market_forecaster.core.forecast_authority as authority

    captured = {}
    local_path = tmp_path / ".local" / "forecast_authority.json"

    monkeypatch.setattr(authority, "SHARED_AUTHORITY_ENABLED", True)
    monkeypatch.setattr(
        authority,
        "shared_authority_write_configuration_status",
        lambda: (True, "ready"),
    )
    monkeypatch.setattr(
        authority,
        "publish_shared_authority",
        lambda payload: captured.setdefault("payload", payload),
    )
    monkeypatch.setattr(authority, "authority_path", lambda repo_root=None: local_path)

    config = default_authority_config()
    config["horizons"]["20"]["calibration_window"] = 250
    saved = save_authority_config(config)

    assert captured["payload"] == saved
    assert local_path.exists()
