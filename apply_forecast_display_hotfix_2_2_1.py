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


def install_plots(bundle_root: Path, package: Path) -> None:
    src = bundle_root / "market_forecaster" / "ui" / "plots.py"
    dst = package / "ui" / "plots.py"
    if src.resolve() == dst.resolve():
        print("[ok] plots.py already extracted in place")
        return
    backup(dst)
    shutil.copy2(src, dst)
    print(f"Installed: {dst}")


def patch_app(app: Path) -> None:
    text = app.read_text(encoding="utf-8")
    original = text

    # Add full history + current pattern marker data to the forecast visualization.
    old = '''            plot_forecast(\n                merged, forecast,\n                f"{req.ticker} — {req.horizon}-Day Forecast",\n                tech_df=stock_df if is_trader() else None,\n                show_technicals=is_trader(),\n            )'''
    new = '''            plot_forecast(\n                merged, forecast,\n                f"{req.ticker} — {req.horizon}-Day Forecast",\n                tech_df=stock_df if is_trader() else None,\n                show_technicals=is_trader(),\n                history_df=prophet_df,\n                pattern_scores=pattern_scores,\n            )'''

    if new in text:
        print("[ok] app.py forecast display already patched")
    elif old in text:
        text = text.replace(old, new, 1)
    else:
        # More tolerant fallback for locally formatted copies.
        pattern = re.compile(
            r'(plot_forecast\(\s*\n\s*merged\s*,\s*forecast\s*,\s*\n\s*f"\{req\.ticker\} — \{req\.horizon\}-Day Forecast"\s*,\s*\n\s*tech_df=stock_df if is_trader\(\) else None\s*,\s*\n\s*show_technicals=is_trader\(\)\s*,)(\s*\n\s*\))',
            re.MULTILINE,
        )
        match = pattern.search(text)
        if not match:
            raise SystemExit("Could not locate plot_forecast(...) call in app.py. Send me that block and I will patch the customized layout.")
        text = text[:match.start()] + match.group(1) + '\n                history_df=prophet_df,\n                pattern_scores=pattern_scores,' + match.group(2) + text[match.end():]

    if text != original:
        backup(app)
        app.write_text(text, encoding="utf-8")
        print(f"Patched: {app}")


def patch_version(config: Path) -> None:
    text = config.read_text(encoding="utf-8")
    new = re.sub(r'__version__\s*=\s*"2\.2\.0"', '__version__ = "2.2.1"', text, count=1)
    if new != text:
        backup(config)
        config.write_text(new, encoding="utf-8")
        print("Version: 2.2.1")
    elif '__version__ = "2.2.1"' in text:
        print("[ok] version already 2.2.1")
    else:
        print("[warn] customized version left unchanged")


def main() -> None:
    repo_root, package = find_repo_and_package()
    bundle_root = Path(__file__).resolve().parent
    print(f"Repository: {repo_root}")
    install_plots(bundle_root, package)
    patch_app(package / "app.py")
    patch_version(package / "config.py")
    print("\nForecast display hotfix 2.2.1 applied.")
    print("Run: python -m compileall -q market_forecaster")
    print("Then start Streamlit and rerun a forecast.")


if __name__ == "__main__":
    main()
