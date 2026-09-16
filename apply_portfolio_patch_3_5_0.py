#!/usr/bin/env python3
"""Install Market Forecaster Portfolio State + Position-Aware Ranking 3.5.0."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

PAYLOAD_NAME = "mf35_payload_v350"


def find_repo_root(script_dir: Path) -> Path:
    for candidate in [Path.cwd().resolve(), script_dir.parent.resolve(), script_dir.resolve()]:
        if (candidate / "market_forecaster" / "app.py").exists():
            return candidate
    raise SystemExit("Could not find market_forecaster_v2 repo root.")


def backup(path: Path, repo_root: Path):
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = path.with_name(path.name + f".portbak_{stamp}")
        shutil.copy2(path, target)
        print(f"backup: {target.relative_to(repo_root)}")


def ensure_after(text: str, anchor: str, addition: str, label: str) -> str:
    if addition.strip() in text:
        return text
    pos = text.find(anchor)
    if pos < 0:
        raise RuntimeError(f"Could not patch {label}: expected anchor not found")
    end = pos + len(anchor)
    return text[:end] + addition + text[end:]


script_dir = Path(__file__).resolve().parent
repo_root = find_repo_root(script_dir)
payload_root = script_dir / PAYLOAD_NAME / "market_forecaster"
if not payload_root.exists():
    raise SystemExit(f"3.5 payload missing: {payload_root}")

config_path = repo_root / "market_forecaster" / "config.py"
config = config_path.read_text(encoding="utf-8")
if '__version__ = "3.5.0"' not in config and '__version__ = "3.4.0"' not in config:
    raise RuntimeError("3.5 requires Market Forecaster 3.4.0")

for rel in [
    "core/portfolio.py",
    "ui/portfolio_panel.py",
    "api/routes/portfolio.py",
    "tests/test_portfolio.py",
]:
    src = payload_root / rel
    dst = repo_root / "market_forecaster" / rel
    if not src.exists():
        raise RuntimeError(f"Missing patch file: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        backup(dst, repo_root)
    shutil.copy2(src, dst)
    print(f"installed: market_forecaster/{rel}")

app_path = repo_root / "market_forecaster" / "app.py"
backup(app_path, repo_root)
app = app_path.read_text(encoding="utf-8")
app = ensure_after(
    app,
    "from market_forecaster.ui.ranking_panel import render_opportunity_ranking_panel\n",
    "from market_forecaster.ui.portfolio_panel import render_portfolio_panel\n",
    "portfolio UI import",
)
app = ensure_after(
    app,
    "        render_opportunity_ranking_panel(req.ticker)\n",
    '        st.markdown("---")\n'
    "        render_portfolio_panel()\n",
    "portfolio Backtest panel",
)
app_path.write_text(app, encoding="utf-8")
print("patched: market_forecaster/app.py")

api_path = repo_root / "market_forecaster" / "api" / "main.py"
backup(api_path, repo_root)
api = api_path.read_text(encoding="utf-8")
api = ensure_after(
    api,
    "from market_forecaster.api.routes import opportunity_ranking as opportunity_ranking_routes\n",
    "from market_forecaster.api.routes import portfolio as portfolio_routes\n",
    "portfolio API import",
)
api = ensure_after(
    api,
    'app.include_router(opportunity_ranking_routes.router, prefix="/api/v1", tags=["Opportunity Ranking"], dependencies=protected)\n',
    'app.include_router(portfolio_routes.router, prefix="/api/v1", tags=["Portfolio"], dependencies=protected)\n',
    "portfolio API registration",
)
api_path.write_text(api, encoding="utf-8")
print("patched: market_forecaster/api/main.py")

backup(config_path, repo_root)
config = config_path.read_text(encoding="utf-8")
if '__version__ = "3.5.0"' not in config:
    config = config.replace('__version__ = "3.4.0"', '__version__ = "3.5.0"', 1)
config_path.write_text(config, encoding="utf-8")
print("patched: market_forecaster/config.py -> 3.5.0")

print("\nPortfolio State + Position-Aware Ranking 3.5.0 installed successfully.")
print("Next:")
print("  python -m compileall -q market_forecaster")
print("  python -m pytest market_forecaster/tests/test_portfolio.py -q")
print("  streamlit run market_forecaster/app.py")
