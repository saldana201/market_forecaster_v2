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
