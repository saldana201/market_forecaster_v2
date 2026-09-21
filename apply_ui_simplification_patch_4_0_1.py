#!/usr/bin/env python3
"""Install Market Forecaster UI/UX Simplification 4.0.1."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

PAYLOAD_NAME = "mf401_payload_v401"


def find_repo_root(script_dir: Path) -> Path:
    for candidate in [Path.cwd().resolve(), script_dir.parent.resolve(), script_dir.resolve()]:
        if (candidate / "market_forecaster" / "app.py").exists():
            return candidate
    raise SystemExit("Could not find market_forecaster_v2 repo root.")


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Could not patch {label}: expected block not found")
    return text.replace(old, new, 1)


def patch_after(text: str, anchor: str, addition: str, label: str) -> str:
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
    raise SystemExit(f"4.0.1 payload missing: {payload_root}")

config_path = repo_root / "market_forecaster" / "config.py"
app_path = repo_root / "market_forecaster" / "app.py"
sidebar_path = repo_root / "market_forecaster" / "ui" / "sidebar.py"

config = config_path.read_text(encoding="utf-8")
if '__version__ = "4.0.1"' not in config and '__version__ = "4.0.0"' not in config:
    raise RuntimeError("4.0.1 requires Market Forecaster 4.0.0")

payload_files = [
    "ui/forecast_dashboard.py",
    "ui/research_workspace.py",
    "ui/system_health_workspace.py",
    "ui/advanced_tools_panel.py",
    "ui/sidebar.py",
    "tests/test_forecast_dashboard.py",
]
for rel in payload_files:
    src = payload_root / rel
    if not src.exists():
        raise RuntimeError(f"Missing patch file: {src}")
    compile(src.read_text(encoding="utf-8"), str(src), "exec")

app = app_path.read_text(encoding="utf-8")
app_new = patch_after(
    app,
    "from market_forecaster.ui.forecast_intelligence_panel import render_forecast_intelligence_panel\n",
    "from market_forecaster.ui.forecast_dashboard import render_forecast_dashboard\n"
    "from market_forecaster.ui.research_workspace import render_research_workspace\n"
    "from market_forecaster.ui.system_health_workspace import render_system_health_workspace\n"
    "from market_forecaster.ui.advanced_tools_panel import render_advanced_tools_panel\n",
    "4.0.1 workspace imports",
)

old_header = '''st.write(\n    "Forecast and validate future market-price scenarios for stocks & crypto. "\n    "Built around leakage-controlled research, uncertainty, and repeatable out-of-sample evidence."\n)'''
new_header = '''st.write(\n    "Clear multi-horizon market forecasts first. Research, system diagnostics, "\n    "and legacy model controls are available when you need them."\n)'''
app_new = replace_exact(app_new, old_header, new_header, "plain-language header")

old_tabs = '''# ===================================================================\n# Tabs — progressive based on mode\n# ===================================================================\nif get_mode() == "Simple":\n    tabs = st.tabs(["🔮 Forecast", "📚 Help"])\n    tab_forecast, tab_help = tabs\n    tab_ensemble = tab_sentiment = tab_seasonal = tab_backtest = tab_patterns = None\nelif get_mode() == "Trader":\n    tabs = st.tabs(["🔮 Forecast", "📊 Ensemble", "📅 Seasonal", "🔁 Backtest", "📚 Help"])\n    tab_forecast, tab_ensemble, tab_seasonal, tab_backtest, tab_help = tabs\n    tab_sentiment = tab_patterns = None\nelse:  # Analyst\n    tabs = st.tabs(["🔮 Forecast", "📊 Ensemble", "💭 Sentiment", "📅 Seasonal", "🔁 Backtest", "📈 Patterns", "📚 Help"])\n    tab_forecast, tab_ensemble, tab_sentiment, tab_seasonal, tab_backtest, tab_patterns, tab_help = tabs\n'''
new_tabs = '''# ===================================================================\n# Workspaces — forecast first, complexity on demand (4.0.1)\n# ===================================================================\ntab_forecast, tab_research, tab_health, tab_advanced, tab_help = st.tabs([\n    "🔮 Forecast",\n    "🧪 Research Lab",\n    "🩺 System Health",\n    "⚙️ Advanced",\n    "📚 Help",\n])\n\n# Legacy sections remain available inside Advanced instead of appearing as\n# top-level product concepts. Backtest/research diagnostics are handled by\n# the dedicated Research Lab and System Health workspaces.\ntab_ensemble = tab_advanced if is_trader() else None\ntab_sentiment = tab_advanced if is_analyst() else None\ntab_seasonal = tab_advanced if is_trader() else None\ntab_patterns = tab_advanced if is_analyst() else None\ntab_backtest = None\n\nwith tab_forecast:\n    render_forecast_dashboard(req.ticker)\n\nwith tab_research:\n    render_research_workspace(req.ticker)\n\nwith tab_health:\n    render_system_health_workspace(req)\n\nwith tab_advanced:\n    st.header("Advanced / Legacy Tools")\n    st.caption(\n        "Older Prophet, ensemble, seasonal, sentiment, pattern, ranking, and portfolio tools remain here for comparison and compatibility. "\n        "They do not replace the canonical 4.0 Forecast Contract shown on the Forecast page."\n    )\n    render_advanced_tools_panel(req.ticker)\n'''
app_new = replace_exact(app_new, old_tabs, new_tabs, "workspace navigation")

app_new = replace_exact(
    app_new,
    'if st.session_state.pop("run_autotune", False):\n    with tab_forecast:',
    'if st.session_state.pop("run_autotune", False):\n    with tab_advanced:',
    "AutoTune relocation",
)
app_new = replace_exact(
    app_new,
    '# Forecast tab\n# ===================================================================\nwith tab_forecast:',
    '# Advanced legacy forecast workflow\n# ===================================================================\nwith tab_advanced:',
    "legacy forecast relocation",
)
app_new = app_new.replace(
    'label="Integrated Signal" if integrated else "Trading Signal",',
    'label="Legacy Integrated Signal" if integrated else "Legacy Model Signal",',
    1,
)

old_modes_help = '''### Modes\n- **Simple** — Ticker + preset + one-click forecast. Best for quick checks.\n- **Trader** — Adds horizon/holdout controls, AutoTune, backtest, ensemble, and exports.\n- **Analyst** — Full access to Prophet parameters, pattern diagnostics, and all model internals.\n\n### AutoTune (Trader mode)'''
new_modes_help = '''### Workspaces\n- **Forecast** — plain-language 1D / 5D / 10D / 20D outlook from the canonical Forecast Contract.\n- **Research Lab** — guided model, feature, calibration, and Forecast Authority research.\n- **System Health** — data freshness, providers, operations, governance, and validation diagnostics.\n- **Advanced** — legacy Prophet/ensemble tools and expert controls kept for comparison and compatibility.\n\n### Advanced / Legacy AutoTune'''
app_new = replace_exact(app_new, old_modes_help, new_modes_help, "help workspace copy")
app_new = app_new.replace(
    "3. Click **🚀 Run Forecast**\n4. Read the plain-English insight at the top of the results",
    "3. Open **Forecast** and click **Generate Forecast** (or **Refresh Forecast**)\n4. Read the plain-English outlook, probability, and expected range",
    1,
)
app_new = app_new.replace(
    "### Signals\nThe integrated signal combines",
    "### Legacy Signals\nThe Advanced workspace retains the older integrated signal for comparison. It combines",
    1,
)
compile(app_new, str(app_path), "exec")

config_new = config
if '__version__ = "4.0.1"' not in config_new:
    config_new = config_new.replace('__version__ = "4.0.0"', '__version__ = "4.0.1"', 1)
compile(config_new, str(config_path), "exec")

# Only write after every payload and app/config patch has passed preflight.
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_root = repo_root / ".patch_backups" / f"v4_0_1_{stamp}"
backup_root.mkdir(parents=True, exist_ok=True)

for original in [app_path, config_path, sidebar_path]:
    rel = original.relative_to(repo_root)
    target = backup_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(original, target)
    print(f"backup: {target.relative_to(repo_root)}")

for rel in payload_files:
    src = payload_root / rel
    dst = repo_root / "market_forecaster" / rel
    if dst.exists() and dst != sidebar_path:
        old = backup_root / "market_forecaster" / rel
        old.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dst, old)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"installed: market_forecaster/{rel}")

app_path.write_text(app_new, encoding="utf-8")
config_path.write_text(config_new, encoding="utf-8")

print("patched: market_forecaster/app.py")
print("patched: market_forecaster/config.py -> 4.0.1")
print("replaced: market_forecaster/ui/sidebar.py")
print("\nUI/UX Simplification 4.0.1 installed successfully.")
print("Next:")
print("  python -m compileall -q market_forecaster")
print("  python -m pytest market_forecaster/tests/test_forecast_dashboard.py -q")
print("  streamlit run market_forecaster/app.py")
