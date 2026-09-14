from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

PATCH_VERSION = "2.6.0"


def find_repo_root(script_dir: Path) -> Path:
    candidates = [Path.cwd().resolve(), script_dir.parent.resolve(), script_dir.resolve()]
    for candidate in candidates:
        if (candidate / "market_forecaster" / "app.py").exists():
            return candidate
    raise SystemExit(
        "Could not locate repo root. Run this from market_forecaster_v2, or keep the patch folder directly inside that repo root."
    )


def backup(path: Path, backup_root: Path) -> None:
    rel = path.relative_to(path.parents[1]) if path.name == "app.py" else None
    target = backup_root / path.name if rel is None else backup_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Patch anchor not found for {label}. Your file may differ from the expected 2.5 baseline.")
    return text.replace(old, new, 1)


def patch_app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from market_forecaster.ui.consensus_panel import render_production_consensus_panel\n",
        "from market_forecaster.ui.consensus_panel import render_production_consensus_panel\n"
        "from market_forecaster.ui.options_panel import render_options_flow_panel\n",
        "app options panel import",
    )
    text = replace_once(
        text,
        "from market_forecaster.core.signals import compute_basic_signal, compute_integrated_signal\n",
        "from market_forecaster.core.signals import compute_basic_signal, compute_integrated_signal\n"
        "from market_forecaster.core.options_flow_v2 import fetch_options_flow_v2, persist_options_snapshot\n",
        "app options core import",
    )
    text = replace_once(
        text,
        "        seasonal_analysis = None\n\n        if req.use_ensemble:\n",
        "        seasonal_analysis = None\n"
        "        options_flow_data = None\n"
        "        st.session_state.pop(\"options_flow_v2\", None)\n\n"
        "        if req.use_options:\n"
        "            with st.spinner(\"Analyzing options flow...\"):\n"
        "                try:\n"
        "                    option_close = get_close_series(stock_df).dropna()\n"
        "                    option_spot = float(option_close.iloc[-1]) if not option_close.empty else None\n"
        "                    options_flow_data = fetch_options_flow_v2(req.ticker, spot=option_spot)\n"
        "                    if options_flow_data.get(\"available\"):\n"
        "                        persist_options_snapshot(options_flow_data)\n"
        "                    st.session_state[\"options_flow_v2\"] = options_flow_data\n"
        "                except Exception as e:\n"
        "                    st.warning(f\"Options flow error: {e}\")\n\n"
        "        if req.use_ensemble:\n",
        "app options fetch block",
    )
    text = replace_once(
        text,
        "        if any([ensemble_result, sentiment_data, seasonal_signal]):\n",
        "        if any([ensemble_result, sentiment_data, seasonal_signal, options_flow_data and options_flow_data.get(\"available\")]):\n",
        "app integrated trigger",
    )
    text = replace_once(
        text,
        "                sentiment_data=sentiment_data,\n                seasonal_signal=seasonal_signal,\n            )\n",
        "                sentiment_data=sentiment_data,\n                seasonal_signal=seasonal_signal,\n"
        "                options_data=options_flow_data,\n            )\n",
        "app integrated options argument",
    )
    text = replace_once(
        text,
        "        result = st.session_state.get(\"ensemble_result\")\n        render_regime_panel(st.session_state.get(\"stock_df\"), result)\n",
        "        result = st.session_state.get(\"ensemble_result\")\n"
        "        render_options_flow_panel(st.session_state.get(\"options_flow_v2\"), st.session_state.get(\"stock_df\"))\n"
        "        render_regime_panel(st.session_state.get(\"stock_df\"), result)\n",
        "app ensemble options panel",
    )
    path.write_text(text, encoding="utf-8")


def patch_signals(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "    seasonal_signal: Optional[dict] = None,\n    window: int = 1,\n",
        "    seasonal_signal: Optional[dict] = None,\n    options_data: Optional[dict] = None,\n    window: int = 1,\n",
        "signals options signature",
    )
    old = '''    # Options score\n    options_score = 0.0\n    try:\n        if "options_sentiment_scaled" in forecast_df.columns:\n            options_score += float(forecast_df["options_sentiment_scaled"].iloc[-window:].mean()) * 0.5\n        if "put_call_ratio_scaled" in forecast_df.columns:\n            options_score -= float(forecast_df["put_call_ratio_scaled"].iloc[-window:].mean()) * 0.5\n    except Exception:\n        pass\n    scores["options"] = np.clip(options_score, -1, 1)\n'''
    new = '''    # Options score. Prefer the current observed Options Flow v2 snapshot.\n    # Historical options regressors are only a fallback when real history exists;\n    # no synthetic options history is created.\n    options_score = 0.0\n    try:\n        if options_data and options_data.get("available"):\n            options_score = float(options_data.get("options_signal_score", 0.0))\n        else:\n            if "options_sentiment_scaled" in forecast_df.columns:\n                options_score += float(forecast_df["options_sentiment_scaled"].iloc[-window:].mean()) * 0.5\n            if "put_call_ratio_scaled" in forecast_df.columns:\n                options_score -= float(forecast_df["put_call_ratio_scaled"].iloc[-window:].mean()) * 0.5\n    except Exception:\n        pass\n    scores["options"] = float(np.clip(options_score, -1, 1))\n'''
    text = replace_once(text, old, new, "signals options scoring")
    path.write_text(text, encoding="utf-8")


def patch_api_main(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from market_forecaster.api.routes import consensus as consensus_routes\n",
        "from market_forecaster.api.routes import consensus as consensus_routes\n"
        "from market_forecaster.api.routes import options as options_routes\n",
        "api options route import",
    )
    text = replace_once(
        text,
        "app.include_router(consensus_routes.router, prefix=\"/api/v1\", tags=[\"Consensus\"], dependencies=protected)\n",
        "app.include_router(consensus_routes.router, prefix=\"/api/v1\", tags=[\"Consensus\"], dependencies=protected)\n"
        "app.include_router(options_routes.router, prefix=\"/api/v1\", tags=[\"Options Flow\"], dependencies=protected)\n",
        "api options route include",
    )
    path.write_text(text, encoding="utf-8")


def patch_config(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{PATCH_VERSION}"', text, count=1)
    if count != 1:
        raise RuntimeError("Could not update __version__ in config.py")
    path.write_text(updated, encoding="utf-8")


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    repo = find_repo_root(script_dir)
    payload = script_dir / "payload" / "market_forecaster"
    if not payload.exists():
        raise SystemExit(f"Payload not found: {payload}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = repo / f".patch_backups/options_flow_2.6.0_{stamp}"
    backup_root.mkdir(parents=True, exist_ok=True)

    targets = [
        repo / "market_forecaster" / "app.py",
        repo / "market_forecaster" / "core" / "signals.py",
        repo / "market_forecaster" / "api" / "main.py",
        repo / "market_forecaster" / "config.py",
    ]
    for target in targets:
        if not target.exists():
            raise SystemExit(f"Required file missing: {target}")
        rel = target.relative_to(repo)
        backup_path = backup_root / rel
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup_path)

    for src in payload.rglob("*"):
        if src.is_file():
            rel = src.relative_to(payload)
            dst = repo / "market_forecaster" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    patch_app(repo / "market_forecaster" / "app.py")
    patch_signals(repo / "market_forecaster" / "core" / "signals.py")
    patch_api_main(repo / "market_forecaster" / "api" / "main.py")
    patch_config(repo / "market_forecaster" / "config.py")

    print(f"Market Forecaster Options Flow v{PATCH_VERSION} applied successfully.")
    print(f"Backups: {backup_root}")
    print("Next:")
    print("  python -m compileall -q market_forecaster")
    print("  pytest market_forecaster/tests/test_options_flow_v2.py -q")
    print("  streamlit run market_forecaster/app.py")


if __name__ == "__main__":
    main()
