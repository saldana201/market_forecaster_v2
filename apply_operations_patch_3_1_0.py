#!/usr/bin/env python3
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

PAYLOAD_NAME = "mf31_payload_v310"


def find_repo_root(script_dir: Path) -> Path:
    for candidate in [Path.cwd().resolve(), script_dir.parent.resolve(), script_dir.resolve()]:
        if (candidate / "market_forecaster" / "app.py").exists():
            return candidate
    raise SystemExit("Could not find market_forecaster_v2 repo root.")


def backup(path: Path, repo_root: Path):
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = path.with_name(path.name + f".opsbak_{stamp}")
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


def insert_after_line(text: str, needle: str, block_lines: list[str], marker: str, label: str, indent_extra: int = 0) -> str:
    if marker in text:
        return text
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if needle in line:
            base_indent = line[:len(line) - len(line.lstrip())] + (" " * indent_extra)
            block = "".join(base_indent + x + "\n" for x in block_lines)
            lines.insert(i + 1, block)
            return "".join(lines)
    raise RuntimeError(f"Could not patch {label}: line containing {needle!r} not found")


def insert_before_line(text: str, needle: str, block_lines: list[str], marker: str, label: str, indent_extra: int = 0) -> str:
    if marker in text:
        return text
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if needle in line:
            base_indent = line[:len(line) - len(line.lstrip())] + (" " * indent_extra)
            block = "".join(base_indent + x + "\n" for x in block_lines)
            lines.insert(i, block)
            return "".join(lines)
    raise RuntimeError(f"Could not patch {label}: line containing {needle!r} not found")


script_dir = Path(__file__).resolve().parent
repo_root = find_repo_root(script_dir)
payload_root = script_dir / PAYLOAD_NAME / "market_forecaster"
if not payload_root.exists():
    raise SystemExit(
        f"3.1 payload missing: {payload_root}. Keep the extracted patch folder intact."
    )

for rel in [
    "core/operations.py",
    "ui/operations_panel.py",
    "api/routes/operations.py",
    "scripts/ops_maintenance.py",
    "tests/test_operations.py",
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

# ---------------- App ----------------
app_path = repo_root / "market_forecaster" / "app.py"
backup(app_path, repo_root)
app = app_path.read_text(encoding="utf-8")

app = ensure_after(
    app,
    "from market_forecaster.ui.deployment_panel import render_deployment_policy_panel\n",
    "from market_forecaster.ui.operations_panel import render_operations_panel\n",
    "operations UI import",
)
app = ensure_after(
    app,
    "from market_forecaster.core.options_flow_v2 import fetch_options_flow_v2, persist_options_snapshot\n",
    "from market_forecaster.core.operations import record_operation_event\n",
    "operations event import",
)

app = insert_after_line(
    app,
    "if stock_df.empty:",
    ['record_operation_event(req.ticker, "data_fetch", "ERROR", "Provider returned no market data")'],
    'record_operation_event(req.ticker, "data_fetch", "ERROR"',
    "empty-data telemetry",
    indent_extra=4,
)

app = insert_after_line(
    app,
    "stock_df = add_technical_indicators(stock_df)",
    [
        "record_operation_event(",
        '    req.ticker, "data_fetch", "SUCCESS", "Market data fetch completed",',
        '    metadata={"rows": len(stock_df), "provider": stock_df.attrs.get("provider")},',
        ")",
    ],
    'record_operation_event(' + "\n" + '                req.ticker, "data_fetch", "SUCCESS"',
    "data-fetch success telemetry",
)

for needle, component, label in [
    ('st.warning(f"Options flow error: {e}")', "options_flow", "options telemetry"),
    ('st.warning(f"Ensemble error: {e}")', "ensemble", "ensemble telemetry"),
    ('st.warning(f"Sentiment error: {e}")', "sentiment", "sentiment telemetry"),
    ('st.warning(f"Seasonal error: {e}")', "seasonal", "seasonal telemetry"),
]:
    app = insert_before_line(
        app,
        needle,
        [f'record_operation_event(req.ticker, "{component}", "ERROR", str(e))'],
        f'record_operation_event(req.ticker, "{component}", "ERROR"',
        label,
    )

app = insert_after_line(
    app,
    "st.info(insight_text)",
    [
        "record_operation_event(",
        '    req.ticker, "forecast_pipeline", "SUCCESS", "Forecast pipeline completed",',
        '    metadata={"horizon": req.horizon, "ensemble_enabled": bool(req.use_ensemble)},',
        ")",
    ],
    '"forecast_pipeline", "SUCCESS"',
    "forecast success telemetry",
)

app = insert_after_line(
    app,
    'render_governance_panel(req.ticker, st.session_state.get("stock_df"))',
    [
        'st.markdown("---")',
        'render_operations_panel(req.ticker, st.session_state.get("stock_df"))',
    ],
    "render_operations_panel(req.ticker",
    "Backtest operations panel",
)

app_path.write_text(app, encoding="utf-8")
print("patched: market_forecaster/app.py")

# ---------------- Consensus ----------------
consensus_path = repo_root / "market_forecaster" / "ui" / "consensus_panel.py"
backup(consensus_path, repo_root)
consensus = consensus_path.read_text(encoding="utf-8")
consensus = ensure_after(
    consensus,
    "from market_forecaster.core.deployment_policy import build_deployment_decision\n",
    "from market_forecaster.core.operations import run_operations_cycle\n",
    "consensus operations import",
)
consensus = insert_before_line(
    consensus,
    "xgb_count = len(result.xgb_anchors)",
    [
        "try:",
        "    operations_cycle = run_operations_cycle(ticker, stock_df, force=False)",
        '    st.session_state["operations_cycle_state"] = operations_cycle',
        "except Exception as exc:",
        '    st.caption(f"Operations maintenance unavailable: {exc}")',
        "",
    ],
    'st.session_state["operations_cycle_state"]',
    "consensus operations hook",
)
consensus_path.write_text(consensus, encoding="utf-8")
print("patched: market_forecaster/ui/consensus_panel.py")

# ---------------- API ----------------
api_path = repo_root / "market_forecaster" / "api" / "main.py"
backup(api_path, repo_root)
api = api_path.read_text(encoding="utf-8")
api = ensure_after(
    api,
    "from market_forecaster.api.routes import deployment_policy as deployment_policy_routes\n",
    "from market_forecaster.api.routes import operations as operations_routes\n",
    "operations API import",
)
api = ensure_after(
    api,
    'app.include_router(deployment_policy_routes.router, prefix="/api/v1", tags=["Deployment Policy"], dependencies=protected)\n',
    'app.include_router(operations_routes.router, prefix="/api/v1", tags=["Operations"], dependencies=protected)\n',
    "operations API registration",
)
api_path.write_text(api, encoding="utf-8")
print("patched: market_forecaster/api/main.py")

# ---------------- Version ----------------
config_path = repo_root / "market_forecaster" / "config.py"
backup(config_path, repo_root)
config = config_path.read_text(encoding="utf-8")
if '__version__ = "3.1.0"' not in config:
    if '__version__ = "3.0.1"' not in config:
        raise RuntimeError("Expected stabilized 3.0.1 baseline")
    config = config.replace('__version__ = "3.0.1"', '__version__ = "3.1.0"', 1)
config_path.write_text(config, encoding="utf-8")
print("patched: market_forecaster/config.py -> 3.1.0")

print("\nProduction Operations 3.1.0 installed successfully.")
print("Next:")
print("  python -m compileall -q market_forecaster")
print("  python -m pytest market_forecaster/tests/test_operations.py -q")
print("  streamlit run market_forecaster/app.py")
