#!/usr/bin/env python3
"""Install Market Forecaster Forecast Audit + Governance 2.9.0."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def find_repo_root(package_dir: Path) -> Path:
    candidates = [Path.cwd().resolve(), package_dir.parent.resolve(), package_dir.resolve()]
    for candidate in candidates:
        if (candidate / "market_forecaster" / "app.py").exists():
            return candidate
    raise SystemExit(
        "Could not find market_forecaster_v2 repo root. "
        "Run from repo root or extract this patch folder directly under it."
    )


def backup(path: Path, repo_root: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = path.with_name(path.name + f".bak_{stamp}")
    shutil.copy2(path, target)
    print(f"backup: {target.relative_to(repo_root)}")


def replace_once(text: str, needle: str, replacement: str, label: str) -> str:
    if replacement in text:
        return text
    if needle not in text:
        raise RuntimeError(f"Could not patch {label}: expected anchor not found")
    return text.replace(needle, replacement, 1)


package_dir = Path(__file__).resolve().parent
repo_root = find_repo_root(package_dir)
payload_root = package_dir / "payload" / "market_forecaster"
if not payload_root.exists():
    raise SystemExit(f"Payload not found: {payload_root}")

for source in payload_root.rglob("*"):
    if source.is_dir():
        continue
    rel = source.relative_to(payload_root)
    dest = repo_root / "market_forecaster" / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        backup(dest, repo_root)
    shutil.copy2(source, dest)
    print(f"installed: market_forecaster/{rel.as_posix()}")

consensus_path = repo_root / "market_forecaster" / "ui" / "consensus_panel.py"
backup(consensus_path, repo_root)
consensus = consensus_path.read_text(encoding="utf-8")
consensus = replace_once(
    consensus,
    "from market_forecaster.core.production_consensus import build_production_consensus\n",
    "from market_forecaster.core.production_consensus import build_production_consensus\n"
    "from market_forecaster.core.forecast_audit import record_consensus_audit\n",
    "consensus audit import",
)
audit_anchor = '    st.session_state["adaptive_production_consensus_result"] = result\n'
audit_hook = """    st.session_state["adaptive_production_consensus_result"] = result

    # Append-only audit: exact Streamlit reruns are fingerprint-deduplicated.
    try:
        audit_run_id, audit_created = record_consensus_audit(
            ticker,
            result,
            ensemble_result,
            stock_df,
            options_promotion=promotion,
        )
        st.session_state["forecast_audit_run_id"] = audit_run_id
        st.session_state["forecast_audit_created"] = audit_created
    except Exception as exc:
        st.caption(f"Forecast audit unavailable: {exc}")
"""
consensus = replace_once(consensus, audit_anchor, audit_hook, "consensus audit hook")
consensus_path.write_text(consensus, encoding="utf-8")
print("patched: market_forecaster/ui/consensus_panel.py")

app_path = repo_root / "market_forecaster" / "app.py"
backup(app_path, repo_root)
app = app_path.read_text(encoding="utf-8")
app = replace_once(
    app,
    "from market_forecaster.ui.options_history_panel import render_options_history_panel\n",
    "from market_forecaster.ui.options_history_panel import render_options_history_panel\n"
    "from market_forecaster.ui.governance_panel import render_governance_panel\n",
    "app governance import",
)
app = replace_once(
    app,
    '        st.header("🔁 Prophet Backtest")\n        render_options_history_panel(req.ticker, st.session_state.get("stock_df"))\n',
    '        st.header("🔁 Prophet Backtest")\n'
    '        render_governance_panel(req.ticker, st.session_state.get("stock_df"))\n'
    '        st.markdown("---")\n'
    '        render_options_history_panel(req.ticker, st.session_state.get("stock_df"))\n',
    "Backtest governance panel",
)
app_path.write_text(app, encoding="utf-8")
print("patched: market_forecaster/app.py")

api_path = repo_root / "market_forecaster" / "api" / "main.py"
backup(api_path, repo_root)
api = api_path.read_text(encoding="utf-8")
api = replace_once(
    api,
    "from market_forecaster.api.routes import options_promotion as options_promotion_routes\n",
    "from market_forecaster.api.routes import options_promotion as options_promotion_routes\n"
    "from market_forecaster.api.routes import audit as audit_routes\n",
    "API audit import",
)
api = replace_once(
    api,
    'app.include_router(options_promotion_routes.router, prefix="/api/v1", tags=["Options Promotion"], dependencies=protected)\n',
    'app.include_router(options_promotion_routes.router, prefix="/api/v1", tags=["Options Promotion"], dependencies=protected)\n'
    'app.include_router(audit_routes.router, prefix="/api/v1", tags=["Forecast Audit"], dependencies=protected)\n',
    "API audit registration",
)
api_path.write_text(api, encoding="utf-8")
print("patched: market_forecaster/api/main.py")

config_path = repo_root / "market_forecaster" / "config.py"
backup(config_path, repo_root)
config = config_path.read_text(encoding="utf-8")
if '__version__ = "2.9.0"' not in config:
    if '__version__ = "2.8.0"' not in config:
        raise RuntimeError("Expected Market Forecaster 2.8.0 baseline in config.py")
    config = config.replace('__version__ = "2.8.0"', '__version__ = "2.9.0"', 1)
config_path.write_text(config, encoding="utf-8")
print("patched: market_forecaster/config.py -> 2.9.0")

print("\nForecast Audit + Governance 2.9.0 installed successfully.")
print("Next:")
print("  python -m compileall -q market_forecaster")
print("  pytest market_forecaster/tests/test_forecast_audit.py -q")
print("  streamlit run market_forecaster/app.py")
