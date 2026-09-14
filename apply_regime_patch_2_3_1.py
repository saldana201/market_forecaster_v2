from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path


def find_repo_and_package() -> tuple[Path, Path]:
    cwd = Path.cwd()
    if (cwd / "market_forecaster" / "app.py").exists():
        return cwd, cwd / "market_forecaster"
    if (cwd / "app.py").exists() and (cwd / "core").exists():
        return cwd.parent, cwd
    raise SystemExit("Run this script from the market_forecaster_v2 repo root or from the market_forecaster folder.")


def backup(path: Path) -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = path.with_suffix(path.suffix + f".bak_{stamp}")
    shutil.copy2(path, dest)
    print(f"Backup: {dest}")


def copy_overlay(bundle_root: Path, repo_root: Path) -> None:
    source = bundle_root / "payload" / "market_forecaster"
    target = repo_root / "market_forecaster"
    if not source.exists():
        # If the payload folder is no longer present, only continue when the
        # expected installed modules already exist in the target package.
        required = [
            target / "core" / "regime.py",
            target / "core" / "volatility.py",
            target / "ui" / "regime_panel.py",
            target / "api" / "routes" / "regime.py",
        ]
        if all(path.exists() for path in required):
            print("[ok] regime payload already installed")
            return
        raise SystemExit(
            f"Patch payload not found at {source}. Re-extract the 2.3.1 ZIP at the repo root and rerun."
        )
    for path in source.rglob("*"):
        if path.is_dir():
            continue
        if "__pycache__" in path.parts or ".pytest_cache" in path.parts or path.suffix == ".pyc":
            continue
        relative = path.relative_to(source)
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            backup(dest)
        shutil.copy2(path, dest)
        print(f"Installed: market_forecaster/{relative.as_posix()}")


def patch_app(app: Path) -> None:
    text = app.read_text(encoding="utf-8")
    original = text

    regime_import = "from market_forecaster.ui.regime_panel import render_regime_panel"
    if regime_import not in text:
        markers = [
            "from market_forecaster.ui.validation_panel import render_validation_panel",
            "from market_forecaster.ui.insights import generate_forecast_insight, pattern_bias_label",
        ]
        for marker in markers:
            if marker in text:
                text = text.replace(marker, marker + "\n" + regime_import, 1)
                break
        else:
            raise SystemExit("Could not locate UI import marker in app.py")

    # Arm the ensemble with a regime routing prior learned by the Validation Lab.
    if 'weights=st.session_state.get("regime_routing_weights")' not in text:
        pattern = re.compile(
            r'ensemble_result\s*=\s*run_ensemble_forecast\(req\.ticker,\s*stock_df,\s*req\.horizon\s*\)',
            re.MULTILINE,
        )
        replacement = (
            'ensemble_result = run_ensemble_forecast(\n'
            '                        req.ticker, stock_df, req.horizon,\n'
            '                        weights=st.session_state.get("regime_routing_weights"),\n'
            '                    )'
        )
        text, count = pattern.subn(replacement, text, count=1)
        if count == 0:
            # Accept already-formatted calls that do not yet include weights.
            pattern2 = re.compile(
                r'ensemble_result\s*=\s*run_ensemble_forecast\(\s*req\.ticker\s*,\s*stock_df\s*,\s*req\.horizon\s*,?\s*\)',
                re.MULTILINE,
            )
            text, count = pattern2.subn(replacement, text, count=1)
        if count == 0:
            raise SystemExit("Could not locate run_ensemble_forecast(...) call in app.py")

    regime_call = '        render_regime_panel(st.session_state.get("stock_df"), result)\n'
    if regime_call not in text:
        marker = '        result = st.session_state.get("ensemble_result")\n'
        if marker not in text:
            raise SystemExit("Could not locate Ensemble tab result marker in app.py")
        text = text.replace(marker, marker + regime_call, 1)

    if text != original:
        backup(app)
        app.write_text(text, encoding="utf-8")
        print(f"Patched: {app}")
    else:
        print("[ok] app.py regime integration already applied")


def patch_api_main(main_py: Path) -> None:
    text = main_py.read_text(encoding="utf-8")
    original = text

    route_import = "from market_forecaster.api.routes import regime as regime_routes"
    if route_import not in text:
        marker = "from market_forecaster.api.routes import model_zoo as model_zoo_routes"
        if marker not in text:
            marker = "from market_forecaster.api.routes import signals as signal_routes"
        if marker not in text:
            raise SystemExit("Could not locate API route import marker")
        text = text.replace(marker, marker + "\n" + route_import, 1)

    include = 'app.include_router(regime_routes.router, prefix="/api/v1", tags=["Regime"], dependencies=protected)'
    if include not in text:
        marker = 'app.include_router(model_zoo_routes.router, prefix="/api/v1", tags=["Model Zoo"], dependencies=protected)'
        if marker not in text:
            marker = 'app.include_router(autotune_routes.router, prefix="/api/v1", tags=["AutoTune"], dependencies=protected)'
        if marker not in text:
            raise SystemExit("Could not locate API include marker")
        text = text.replace(marker, marker + "\n" + include, 1)

    if text != original:
        backup(main_py)
        main_py.write_text(text, encoding="utf-8")
        print(f"Patched: {main_py}")
    else:
        print("[ok] api/main.py regime route already applied")


def patch_version(config: Path) -> None:
    text = config.read_text(encoding="utf-8")
    new = re.sub(r'__version__\s*=\s*"2\.2\.1"', '__version__ = "2.3.0"', text, count=1)
    if new == text:
        new = re.sub(r'__version__\s*=\s*"2\.2\.0"', '__version__ = "2.3.0"', text, count=1)
    if new != text:
        backup(config)
        config.write_text(new, encoding="utf-8")
        print("Version: 2.3.0")
    elif '__version__ = "2.3.0"' in text:
        print("[ok] version already 2.3.0")
    else:
        print("[warn] customized version left unchanged")


def main() -> None:
    repo_root, package = find_repo_and_package()
    bundle_root = Path(__file__).resolve().parent
    print(f"Repository: {repo_root}")
    copy_overlay(bundle_root, repo_root)
    patch_app(package / "app.py")
    patch_api_main(package / "api" / "main.py")
    patch_version(package / "config.py")
    print("\nVolatility + Regime Engine 2.3.1 repair applied.")
    print("Run: python -m compileall -q market_forecaster && pytest")
    print("Then start Streamlit and run a forecast. Use Backtest > Production Model Zoo to learn routing priors.")


if __name__ == "__main__":
    main()
