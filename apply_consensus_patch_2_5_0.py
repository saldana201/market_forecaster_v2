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
            target / "core" / "production_consensus.py",
            target / "ui" / "consensus_panel.py",
            target / "api" / "routes" / "consensus.py",
        ]
        if all(p.exists() for p in required):
            print("[ok] Consensus payload already installed")
            return
        raise SystemExit(f"Patch payload not found at {source}. Re-extract the 2.5.0 ZIP and rerun.")

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

    import_line = "from market_forecaster.ui.consensus_panel import render_production_consensus_panel"
    if import_line not in text:
        markers = [
            "from market_forecaster.ui.xgb_panel import render_xgb_panel",
            "from market_forecaster.ui.regime_panel import render_regime_panel",
            "from market_forecaster.ui.validation_panel import render_validation_panel",
        ]
        for marker in markers:
            if marker in text:
                text = text.replace(marker, marker + "\n" + import_line, 1)
                break
        else:
            raise SystemExit("Could not locate Ensemble UI import marker in app.py")

    call_text = (
        'render_production_consensus_panel(st.session_state.get("ensemble_result"), '
        'st.session_state.get("xgb_multihorizon_result"), req.ticker)'
    )
    if call_text not in text:
        pattern = re.compile(
            r'(?m)^(?P<indent>[ \t]*)render_xgb_panel\(st\.session_state\.get\("stock_df"\),\s*req\.ticker,\s*req\.interval\)\s*$'
        )
        match = pattern.search(text)
        if not match:
            raise SystemExit("Could not locate render_xgb_panel(...) in app.py. Apply 2.4.0 first.")
        indent = match.group("indent")
        insertion = match.group(0) + "\n" + indent + call_text
        text = text[:match.start()] + insertion + text[match.end():]

    if text != original:
        backup(app)
        app.write_text(text, encoding="utf-8")
        print(f"Patched: {app}")
    else:
        print("[ok] app.py consensus integration already applied")


def patch_api_main(main_py: Path) -> None:
    text = main_py.read_text(encoding="utf-8")
    original = text

    route_import = "from market_forecaster.api.routes import consensus as consensus_routes"
    if route_import not in text:
        markers = [
            "from market_forecaster.api.routes import xgb as xgb_routes",
            "from market_forecaster.api.routes import regime as regime_routes",
            "from market_forecaster.api.routes import model_zoo as model_zoo_routes",
        ]
        for marker in markers:
            if marker in text:
                text = text.replace(marker, marker + "\n" + route_import, 1)
                break
        else:
            raise SystemExit("Could not locate API route import marker in api/main.py")

    include = 'app.include_router(consensus_routes.router, prefix="/api/v1", tags=["Consensus"], dependencies=protected)'
    if include not in text:
        markers = [
            'app.include_router(xgb_routes.router, prefix="/api/v1", tags=["XGBoost"], dependencies=protected)',
            'app.include_router(regime_routes.router, prefix="/api/v1", tags=["Regime"], dependencies=protected)',
            'app.include_router(model_zoo_routes.router, prefix="/api/v1", tags=["Model Zoo"], dependencies=protected)',
        ]
        for marker in markers:
            if marker in text:
                text = text.replace(marker, marker + "\n" + include, 1)
                break
        else:
            raise SystemExit("Could not locate authenticated API router include marker")

    if text != original:
        backup(main_py)
        main_py.write_text(text, encoding="utf-8")
        print(f"Patched: {main_py}")
    else:
        print("[ok] api/main.py consensus route already applied")


def patch_version(config: Path) -> None:
    text = config.read_text(encoding="utf-8")
    new = re.sub(r'__version__\s*=\s*"2\.4(?:\.\d+)?"', '__version__ = "2.5.0"', text, count=1)
    if new != text:
        backup(config)
        config.write_text(new, encoding="utf-8")
        print("Version: 2.5.0")
    elif '__version__ = "2.5.0"' in text:
        print("[ok] version already 2.5.0")
    else:
        print("[warn] Customized version string left unchanged")


def main() -> None:
    repo_root, package = find_repo_and_package()
    bundle_root = Path(__file__).resolve().parent
    print(f"Repository: {repo_root}")
    copy_overlay(bundle_root, repo_root)
    patch_app(package / "app.py")
    patch_api_main(package / "api" / "main.py")
    patch_version(package / "config.py")
    print("\nProduction Consensus 2.5.0 applied.")
    print("Then run: python -m compileall -q market_forecaster")
    print("Tests: pytest market_forecaster/tests/test_production_consensus.py market_forecaster/tests/test_xgb_multihorizon.py -q")
    print("Start Streamlit and open Ensemble > XGBoost > Production Consensus.")


if __name__ == "__main__":
    main()
