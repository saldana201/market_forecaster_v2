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
        required = [
            target / "core" / "xgb_multihorizon.py",
            target / "ui" / "xgb_panel.py",
            target / "api" / "routes" / "xgb.py",
        ]
        if all(p.exists() for p in required):
            print("[ok] XGBoost payload already installed")
            return
        raise SystemExit(f"Patch payload not found at {source}. Re-extract the 2.4.0 ZIP and rerun.")

    for path in source.rglob("*"):
        if path.is_dir() or "__pycache__" in path.parts or path.suffix == ".pyc":
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

    import_line = "from market_forecaster.ui.xgb_panel import render_xgb_panel"
    if import_line not in text:
        markers = [
            "from market_forecaster.ui.regime_panel import render_regime_panel",
            "from market_forecaster.ui.validation_panel import render_validation_panel",
            "from market_forecaster.ui.insights import generate_forecast_insight, pattern_bias_label",
        ]
        for marker in markers:
            if marker in text:
                text = text.replace(marker, marker + "\n" + import_line, 1)
                break
        else:
            raise SystemExit("Could not locate UI import marker in app.py")

    call_text = 'render_xgb_panel(st.session_state.get("stock_df"), req.ticker, req.interval)'
    if call_text not in text:
        regime_pattern = re.compile(
            r'(?m)^(?P<indent>[ \t]*)render_regime_panel\(st\.session_state\.get\("stock_df"\),\s*result\)\s*$'
        )
        match = regime_pattern.search(text)
        if match:
            indent = match.group("indent")
            insertion = match.group(0) + "\n" + indent + call_text
            text = text[:match.start()] + insertion + text[match.end():]
        else:
            marker_pattern = re.compile(
                r'(?m)^(?P<indent>[ \t]*)result\s*=\s*st\.session_state\.get\("ensemble_result"\)\s*$'
            )
            match = marker_pattern.search(text)
            if not match:
                raise SystemExit("Could not locate Ensemble tab marker in app.py")
            indent = match.group("indent")
            insertion = match.group(0) + "\n" + indent + call_text
            text = text[:match.start()] + insertion + text[match.end():]

    if text != original:
        backup(app)
        app.write_text(text, encoding="utf-8")
        print(f"Patched: {app}")
    else:
        print("[ok] app.py XGBoost integration already applied")


def patch_api_main(main_py: Path) -> None:
    text = main_py.read_text(encoding="utf-8")
    original = text

    route_import = "from market_forecaster.api.routes import xgb as xgb_routes"
    if route_import not in text:
        markers = [
            "from market_forecaster.api.routes import regime as regime_routes",
            "from market_forecaster.api.routes import model_zoo as model_zoo_routes",
            "from market_forecaster.api.routes import signals as signal_routes",
        ]
        for marker in markers:
            if marker in text:
                text = text.replace(marker, marker + "\n" + route_import, 1)
                break
        else:
            raise SystemExit("Could not locate API route import marker")

    include = 'app.include_router(xgb_routes.router, prefix="/api/v1", tags=["XGBoost"], dependencies=protected)'
    if include not in text:
        markers = [
            'app.include_router(regime_routes.router, prefix="/api/v1", tags=["Regime"], dependencies=protected)',
            'app.include_router(model_zoo_routes.router, prefix="/api/v1", tags=["Model Zoo"], dependencies=protected)',
            'app.include_router(autotune_routes.router, prefix="/api/v1", tags=["AutoTune"], dependencies=protected)',
        ]
        for marker in markers:
            if marker in text:
                text = text.replace(marker, marker + "\n" + include, 1)
                break
        else:
            raise SystemExit("Could not locate API router include marker")

    # Advertise availability on the health endpoint when its dictionary is recognizable.
    health_import = "from market_forecaster.core.xgb_multihorizon import XGBOOST_AVAILABLE"
    if health_import not in text:
        marker = "from market_forecaster.core.ensemble import ARIMA_AVAILABLE, LSTM_AVAILABLE"
        if marker in text:
            text = text.replace(marker, marker + "\n" + health_import, 1)
    if '"xgboost": XGBOOST_AVAILABLE' not in text:
        text = re.sub(
            r'("random_forest"\s*:\s*True\s*,?)',
            r'\1\n            "xgboost": XGBOOST_AVAILABLE,',
            text,
            count=1,
        )

    if text != original:
        backup(main_py)
        main_py.write_text(text, encoding="utf-8")
        print(f"Patched: {main_py}")
    else:
        print("[ok] api/main.py XGBoost route already applied")


def patch_requirements(requirements: Path) -> None:
    text = requirements.read_text(encoding="utf-8") if requirements.exists() else ""
    pattern = re.compile(r"^xgboost[^\n]*$", re.MULTILINE | re.IGNORECASE)
    line = "xgboost==3.1.3"
    if pattern.search(text):
        new = pattern.sub(line, text, count=1)
    else:
        new = text.rstrip() + "\n" + line + "\n"
    if new != text:
        if requirements.exists():
            backup(requirements)
        requirements.write_text(new, encoding="utf-8")
        print("Requirement: xgboost==3.1.3")
    else:
        print("[ok] XGBoost requirement already pinned")


def patch_version(config: Path) -> None:
    text = config.read_text(encoding="utf-8")
    new = re.sub(r'__version__\s*=\s*"2\.3(?:\.\d+)?"', '__version__ = "2.4.0"', text, count=1)
    if new != text:
        backup(config)
        config.write_text(new, encoding="utf-8")
        print("Version: 2.4.0")
    elif '__version__ = "2.4.0"' in text:
        print("[ok] version already 2.4.0")
    else:
        print("[warn] customized version left unchanged")


def main() -> None:
    repo_root, package = find_repo_and_package()
    bundle_root = Path(__file__).resolve().parent
    print(f"Repository: {repo_root}")
    copy_overlay(bundle_root, repo_root)
    patch_app(package / "app.py")
    patch_api_main(package / "api" / "main.py")
    patch_requirements(package / "requirements.txt")
    patch_version(package / "config.py")
    print("\nXGBoost Multi-Horizon 2.4.0 applied.")
    print("Install/update runtime dependency: python -m pip install xgboost==3.1.3")
    print("Then: python -m compileall -q market_forecaster && pytest market_forecaster/tests/test_xgb_multihorizon.py -q")
    print("Start Streamlit and open Ensemble > XGBoost Multi-Horizon Scenarios.")


if __name__ == "__main__":
    main()
