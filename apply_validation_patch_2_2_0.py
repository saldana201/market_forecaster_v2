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
    # When the ZIP is extracted directly over the repo root, payload files are
    # already in place and source == target. Do not walk the entire repository.
    if bundle_root.resolve() == repo_root.resolve():
        print("[ok] patch payload already extracted into repository")
        return
    source = bundle_root / "market_forecaster"
    target = repo_root / "market_forecaster"
    for path in source.rglob("*"):
        if path.is_dir():
            continue
        relative = path.relative_to(source)
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        if path.resolve() == dest.resolve():
            print(f"[ok] already extracted: market_forecaster/{relative.as_posix()}")
            continue
        shutil.copy2(path, dest)
        print(f"Installed: market_forecaster/{relative.as_posix()}")


def patch_app(app: Path) -> None:
    text = app.read_text(encoding="utf-8")
    original = text

    import_line = "from market_forecaster.ui.validation_panel import render_validation_panel"
    if import_line not in text:
        marker = "from market_forecaster.ui.insights import generate_forecast_insight, pattern_bias_label"
        if marker not in text:
            raise SystemExit("Could not locate UI import marker in app.py")
        text = text.replace(marker, marker + "\n" + import_line, 1)

    # Insert the new lab at the top of the existing Backtest tab without replacing legacy diagnostics.
    call = '        render_validation_panel(req, st.session_state.get("stock_df"))\n'
    if call not in text:
        marker = '        st.header("🔁 Prophet Backtest")\n'
        if marker not in text:
            raise SystemExit("Could not locate Backtest header marker in app.py")
        text = text.replace(marker, marker + call + '        st.markdown("---")\n', 1)

    if text != original:
        backup(app)
        app.write_text(text, encoding="utf-8")
        print(f"Patched: {app}")
    else:
        print("[ok] app.py validation panel already applied")


def patch_api_main(main_py: Path) -> None:
    text = main_py.read_text(encoding="utf-8")
    original = text

    route_import = "from market_forecaster.api.routes import model_zoo as model_zoo_routes"
    if route_import not in text:
        marker = "from market_forecaster.api.routes import signals as signal_routes"
        if marker not in text:
            raise SystemExit("Could not locate API route import marker")
        text = text.replace(marker, marker + "\n" + route_import, 1)

    include = 'app.include_router(model_zoo_routes.router, prefix="/api/v1", tags=["Model Zoo"], dependencies=protected)'
    if include not in text:
        marker = 'app.include_router(autotune_routes.router, prefix="/api/v1", tags=["AutoTune"], dependencies=protected)'
        if marker not in text:
            raise SystemExit("Could not locate API include marker")
        text = text.replace(marker, marker + "\n" + include, 1)

    if text != original:
        backup(main_py)
        main_py.write_text(text, encoding="utf-8")
        print(f"Patched: {main_py}")
    else:
        print("[ok] api/main.py model-zoo route already applied")


def patch_config(config: Path) -> None:
    text = config.read_text(encoding="utf-8")
    new = re.sub(r'__version__\s*=\s*"2\.1(?:\.[01])?"', '__version__ = "2.2.0"', text, count=1)
    if new == text and '__version__ = "2.2.0"' not in text:
        print("[warn] version marker not changed; customized version left intact")
        return
    if new != text:
        backup(config)
        config.write_text(new, encoding="utf-8")
        print("Version: 2.2.0")


def main() -> None:
    repo_root, package = find_repo_and_package()
    bundle_root = Path(__file__).resolve().parent
    print(f"Repository: {repo_root}")
    copy_overlay(bundle_root, repo_root)
    patch_app(package / "app.py")
    patch_api_main(package / "api" / "main.py")
    patch_config(package / "config.py")
    print("\nValidation Lab 2.2.0 applied.")
    print("Run: python -m compileall -q market_forecaster && pytest")
    print("Then: streamlit run market_forecaster/app.py (repo root) OR streamlit run app.py (inside package folder)")


if __name__ == "__main__":
    main()
