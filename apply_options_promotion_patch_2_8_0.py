#!/usr/bin/env python3
"""Install Market Forecaster Adaptive Options Promotion 2.8.0."""
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
        "Run from the repo root or extract this patch folder directly under it."
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

# Copy new/replacement modules.
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

# Register protected API route.
api_path = repo_root / "market_forecaster" / "api" / "main.py"
backup(api_path, repo_root)
api = api_path.read_text(encoding="utf-8")
api = replace_once(
    api,
    "from market_forecaster.api.routes import options_history as options_history_routes\n",
    "from market_forecaster.api.routes import options_history as options_history_routes\n"
    "from market_forecaster.api.routes import options_promotion as options_promotion_routes\n",
    "API import",
)
api = replace_once(
    api,
    'app.include_router(options_history_routes.router, prefix="/api/v1", tags=["Options History"], dependencies=protected)\n',
    'app.include_router(options_history_routes.router, prefix="/api/v1", tags=["Options History"], dependencies=protected)\n'
    'app.include_router(options_promotion_routes.router, prefix="/api/v1", tags=["Options Promotion"], dependencies=protected)\n',
    "API registration",
)
api_path.write_text(api, encoding="utf-8")
print("patched: market_forecaster/api/main.py")

# Bump version.
config_path = repo_root / "market_forecaster" / "config.py"
backup(config_path, repo_root)
config = config_path.read_text(encoding="utf-8")
if '__version__ = "2.8.0"' not in config:
    if '__version__ = "2.7.0"' not in config:
        raise RuntimeError("Expected Market Forecaster 2.7.0 baseline in config.py")
    config = config.replace('__version__ = "2.7.0"', '__version__ = "2.8.0"', 1)
config_path.write_text(config, encoding="utf-8")
print("patched: market_forecaster/config.py -> 2.8.0")

print("\nAdaptive Options Promotion 2.8.0 installed successfully.")
print("Next:")
print("  python -m compileall -q market_forecaster")
print("  pytest market_forecaster/tests/test_options_promotion.py -q")
print("  streamlit run market_forecaster/app.py")
