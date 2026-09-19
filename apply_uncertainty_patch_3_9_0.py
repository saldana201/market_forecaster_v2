#!/usr/bin/env python3
"""Install Market Forecaster Probability Calibration & Adaptive Uncertainty 3.9.0."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

PAYLOAD_NAME = "mf39_payload_v390"


def find_repo_root(script_dir: Path) -> Path:
    for candidate in [Path.cwd().resolve(), script_dir.parent.resolve(), script_dir.resolve()]:
        if (candidate / "market_forecaster" / "app.py").exists():
            return candidate
    raise SystemExit("Could not find market_forecaster_v2 repo root.")


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
    raise SystemExit(f"3.9 payload missing: {payload_root}")

config_path = repo_root / "market_forecaster" / "config.py"
app_path = repo_root / "market_forecaster" / "app.py"
api_path = repo_root / "market_forecaster" / "api" / "main.py"

config = config_path.read_text(encoding="utf-8")
if '__version__ = "3.9.0"' not in config and '__version__ = "3.8.0"' not in config:
    raise RuntimeError("3.9 requires Market Forecaster 3.8.0")

payload_files = [
    "core/uncertainty_calibration.py",
    "ui/uncertainty_panel.py",
    "api/routes/uncertainty.py",
    "scripts/uncertainty_research.py",
    "tests/test_uncertainty_calibration.py",
]

# Preflight every payload file before changing the repo.
for rel in payload_files:
    src = payload_root / rel
    if not src.exists():
        raise RuntimeError(f"Missing patch file: {src}")
    compile(src.read_text(encoding="utf-8"), str(src), "exec")

# Preflight app patch in memory.
app = app_path.read_text(encoding="utf-8")
app_new = patch_after(
    app,
    "from market_forecaster.ui.feature_ablation_panel import render_feature_ablation_panel\n",
    "from market_forecaster.ui.uncertainty_panel import render_uncertainty_panel\n",
    "uncertainty UI import",
)
app_new = patch_after(
    app_new,
    "        render_feature_ablation_panel(req.ticker)\n",
    '        st.markdown("---")\n        render_uncertainty_panel(req.ticker)\n',
    "uncertainty Backtest panel",
)
compile(app_new, str(app_path), "exec")

# Preflight API patch in memory.
api = api_path.read_text(encoding="utf-8")
api_new = patch_after(
    api,
    "from market_forecaster.api.routes import feature_ablation as feature_ablation_routes\n",
    "from market_forecaster.api.routes import uncertainty as uncertainty_routes\n",
    "uncertainty API import",
)
api_new = patch_after(
    api_new,
    'app.include_router(feature_ablation_routes.router, prefix="/api/v1", tags=["Feature Ablation"], dependencies=protected)\n',
    'app.include_router(uncertainty_routes.router, prefix="/api/v1", tags=["Forecast Uncertainty"], dependencies=protected)\n',
    "uncertainty API registration",
)
compile(api_new, str(api_path), "exec")

config_new = config
if '__version__ = "3.9.0"' not in config_new:
    config_new = config_new.replace('__version__ = "3.8.0"', '__version__ = "3.9.0"', 1)
compile(config_new, str(config_path), "exec")

# Transactional-style mutation begins only after all preflight checks pass.
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_root = repo_root / ".patch_backups" / f"v3_9_{stamp}"
backup_root.mkdir(parents=True, exist_ok=True)

for original in [app_path, api_path, config_path]:
    rel = original.relative_to(repo_root)
    target = backup_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(original, target)
    print(f"backup: {target.relative_to(repo_root)}")

for rel in payload_files:
    src = payload_root / rel
    dst = repo_root / "market_forecaster" / rel
    if dst.exists():
        old = backup_root / "market_forecaster" / rel
        old.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dst, old)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"installed: market_forecaster/{rel}")

app_path.write_text(app_new, encoding="utf-8")
api_path.write_text(api_new, encoding="utf-8")
config_path.write_text(config_new, encoding="utf-8")

print("patched: market_forecaster/app.py")
print("patched: market_forecaster/api/main.py")
print("patched: market_forecaster/config.py -> 3.9.0")
print("\nProbability Calibration & Adaptive Uncertainty 3.9.0 installed successfully.")
print("Next:")
print("  python -m compileall -q market_forecaster")
print("  python -m pytest market_forecaster/tests/test_uncertainty_calibration.py -q")
print("  streamlit run market_forecaster/app.py")
