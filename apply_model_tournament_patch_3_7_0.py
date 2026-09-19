#!/usr/bin/env python3
"""Install Market Forecaster Model Tournament 3.7.0."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

PAYLOAD_NAME = "mf37_payload_v370"


def find_repo_root(script_dir: Path) -> Path:
    for candidate in [Path.cwd().resolve(), script_dir.parent.resolve(), script_dir.resolve()]:
        if (candidate / "market_forecaster" / "app.py").exists():
            return candidate
    raise SystemExit("Could not find market_forecaster_v2 repo root.")


def preflight_python(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    repo_root = find_repo_root(script_dir)
    payload_root = script_dir / PAYLOAD_NAME / "market_forecaster"
    if not payload_root.exists():
        raise SystemExit(f"3.7 payload missing: {payload_root}")

    config_path = repo_root / "market_forecaster" / "config.py"
    if not config_path.exists():
        raise RuntimeError("market_forecaster/config.py not found")
    config = config_path.read_text(encoding="utf-8")
    if '__version__ = "3.7.0"' not in config and '__version__ = "3.6.0"' not in config:
        raise RuntimeError("3.7 requires Market Forecaster 3.6.0")

    rel_files = [
        "core/model_tournament.py",
        "core/experiment_runner.py",
        "ui/research_panel.py",
        "api/routes/research.py",
        "scripts/research_experiment.py",
        "tests/test_model_tournament.py",
        "tests/test_tournament_runner.py",
        "requirements-research-models.txt",
    ]

    # Full preflight before touching the repo.
    for rel in rel_files:
        src = payload_root / rel
        if not src.exists():
            raise RuntimeError(f"Missing patch file: {src}")
        if src.suffix == ".py":
            preflight_python(src)

    new_config = config
    if '__version__ = "3.7.0"' not in new_config:
        new_config = new_config.replace(
            '__version__ = "3.6.0"',
            '__version__ = "3.7.0"',
            1,
        )
    compile(new_config, str(config_path), "exec")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def backup(path: Path) -> None:
        if path.exists():
            target = path.with_name(path.name + f".tournamentbak_{stamp}")
            shutil.copy2(path, target)
            print(f"backup: {target.relative_to(repo_root)}")

    for rel in rel_files:
        src = payload_root / rel
        dst = repo_root / "market_forecaster" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        backup(dst)
        shutil.copy2(src, dst)
        print(f"installed: market_forecaster/{rel}")

    backup(config_path)
    config_path.write_text(new_config, encoding="utf-8")
    print("patched: market_forecaster/config.py -> 3.7.0")

    print("\nModel Tournament 3.7.0 installed successfully.")
    print("Production runtime remains unchanged; research dependencies are optional.")
    print("Next:")
    print("  python -m compileall -q market_forecaster")
    print("  python -m pytest market_forecaster/tests/test_model_tournament.py market_forecaster/tests/test_tournament_runner.py -q")
    print("  streamlit run market_forecaster/app.py")


if __name__ == "__main__":
    main()
