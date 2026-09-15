#!/usr/bin/env python3
"""Install Market Forecaster Forecast Calibration + Decision Layer 3.3.0."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

PAYLOAD_NAME = "mf33_payload_v330"


def find_repo_root(script_dir: Path) -> Path:
    for candidate in [Path.cwd().resolve(), script_dir.parent.resolve(), script_dir.resolve()]:
        if (candidate / "market_forecaster" / "app.py").exists():
            return candidate
    raise SystemExit("Could not find market_forecaster_v2 repo root.")


def backup(path: Path, repo_root: Path):
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = path.with_name(path.name + f".decisionbak_{stamp}")
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
    raise SystemExit(f"3.3 payload missing: {payload_root}")

config_path = repo_root / "market_forecaster" / "config.py"
config = config_path.read_text(encoding="utf-8")
if '__version__ = "3.3.0"' not in config and '__version__ = "3.2.0"' not in config:
    raise RuntimeError("3.3 requires Market Forecaster 3.2.0")

for rel in [
    "core/decision_layer.py",
    "ui/decision_panel.py",
    "api/routes/decision.py",
    "tests/test_decision_layer.py",
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

# Consensus panel: calculate decision after deployment/audit/operations, persist, render.
consensus_path = repo_root / "market_forecaster" / "ui" / "consensus_panel.py"
backup(consensus_path, repo_root)
consensus = consensus_path.read_text(encoding="utf-8")
consensus = ensure_after(
    consensus,
    "from market_forecaster.core.operations import run_operations_cycle\n",
    "from market_forecaster.core.decision_layer import build_decision_layer, persist_decision_snapshot\n"
    "from market_forecaster.ui.decision_panel import render_decision_panel\n",
    "decision imports",
)

if 'st.session_state["decision_layer_result"]' not in consensus:
    marker = "    xgb_count = len(result.xgb_anchors)\n"
    block = """    decision_result = None
    if deployment is not None and stock_df is not None and not getattr(stock_df, "empty", True):
        try:
            decision_result = build_decision_layer(ticker, deployment, stock_df)
            persist_decision_snapshot(decision_result)
            st.session_state["decision_layer_result"] = decision_result
        except Exception as exc:
            st.caption(f"Decision layer unavailable: {exc}")

"""
    if marker not in consensus:
        raise RuntimeError("Could not patch decision calculation hook")
    consensus = consensus.replace(marker, block + marker, 1)

if "render_decision_panel(decision_result)" not in consensus:
    anchor = '    st.plotly_chart(fig, use_container_width=True)\n'
    consensus = ensure_after(
        consensus,
        anchor,
        '\n    render_decision_panel(decision_result)\n',
        "decision panel render",
    )

consensus_path.write_text(consensus, encoding="utf-8")
print("patched: market_forecaster/ui/consensus_panel.py")

# API route registration.
api_path = repo_root / "market_forecaster" / "api" / "main.py"
backup(api_path, repo_root)
api = api_path.read_text(encoding="utf-8")

if "from market_forecaster.api.routes import decision as decision_routes\n" not in api:
    if "from market_forecaster.api.routes import data_providers as data_provider_routes\n" in api:
        api = ensure_after(
            api,
            "from market_forecaster.api.routes import data_providers as data_provider_routes\n",
            "from market_forecaster.api.routes import decision as decision_routes\n",
            "decision API import",
        )
    else:
        api = ensure_after(
            api,
            "from market_forecaster.api.routes import operations as operations_routes\n",
            "from market_forecaster.api.routes import decision as decision_routes\n",
            "decision API import",
        )

route_line = 'app.include_router(decision_routes.router, prefix="/api/v1", tags=["Decision Layer"], dependencies=protected)\n'
if route_line not in api:
    provider_line = 'app.include_router(data_provider_routes.router, prefix="/api/v1", tags=["Data Providers"], dependencies=protected)\n'
    operations_line = 'app.include_router(operations_routes.router, prefix="/api/v1", tags=["Operations"], dependencies=protected)\n'
    if provider_line in api:
        api = ensure_after(api, provider_line, route_line, "decision API registration")
    else:
        api = ensure_after(api, operations_line, route_line, "decision API registration")

api_path.write_text(api, encoding="utf-8")
print("patched: market_forecaster/api/main.py")

backup(config_path, repo_root)
config = config_path.read_text(encoding="utf-8")
if '__version__ = "3.3.0"' not in config:
    config = config.replace('__version__ = "3.2.0"', '__version__ = "3.3.0"', 1)
config_path.write_text(config, encoding="utf-8")
print("patched: market_forecaster/config.py -> 3.3.0")

print("\nForecast Calibration + Decision Layer 3.3.0 installed successfully.")
print("Next:")
print("  python -m compileall -q market_forecaster")
print("  python -m pytest market_forecaster/tests/test_decision_layer.py -q")
print("  streamlit run market_forecaster/app.py")
