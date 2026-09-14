"""Apply the production-hardening edits that must touch existing app/config files.
Run from the repository root AFTER extracting this ZIP over the repository.
"""
from pathlib import Path
import shutil
import sys

ROOT = Path.cwd()
APP = ROOT / "market_forecaster" / "app.py"
CONFIG = ROOT / "market_forecaster" / "config.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        print(f"[ok] {label} already applied")
        return text
    if old not in text:
        raise RuntimeError(f"Could not locate expected app marker for: {label}")
    print(f"[apply] {label}")
    return text.replace(old, new, 1)


def main() -> int:
    if not APP.exists() or not CONFIG.exists():
        print("Run this script from the market_forecaster_v2 repository root.", file=sys.stderr)
        return 2

    for path in (APP, CONFIG):
        backup = path.with_suffix(path.suffix + ".pre-production-hardening.bak")
        if not backup.exists():
            shutil.copy2(path, backup)

    text = APP.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from market_forecaster.core.data import fetch_stock_data, get_close_series",
        "from market_forecaster.core.data import fetch_stock_data, get_close_series, infer_forecast_freq",
        "import trading-calendar helper",
    )
    text = replace_once(
        text,
        "    prepare_for_prophet, fit_and_forecast, evaluate_holdout,\n",
        "    prepare_for_prophet, fit_and_forecast, evaluate_oos,\n",
        "use OOS evaluator",
    )
    text = replace_once(
        text,
        "        stock_df = append_pattern_features(stock_df, pattern_scores)\n",
        "        # Pattern snapshots remain UI/signal inputs only; do not backfill them through model history.\n",
        "remove pattern-regressor leakage",
    )
    text = replace_once(
        text,
        "                use_options=req.use_options, **model_kwargs,\n",
        "                use_options=req.use_options, future_freq=infer_forecast_freq(req.ticker, req.interval), **model_kwargs,\n",
        "use asset-aware forecast dates",
    )
    text = replace_once(
        text,
        "        metrics = evaluate_holdout(prophet_df, forecast, req.holdout_days)\n",
        """        metrics = evaluate_oos(\n            prophet_df,\n            holdout_days=req.holdout_days,\n            model_kwargs=model_kwargs,\n            use_options=req.use_options,\n            growth_mode=req.growth_mode,\n            normalize_logistic=req.normalize_logistic,\n            n_folds=3,\n            future_freq=infer_forecast_freq(req.ticker, req.interval),\n        )\n""",
        "replace in-sample metrics with rolling OOS metrics",
    )
    text = text.replace('st.subheader("Model Performance")', 'st.subheader("Out-of-Sample Model Performance")')
    text = text.replace(
        "Scores are fed into the forecast model as regressors.",
        "Scores are current-snapshot signal inputs only; they are not historical model regressors until a causal pattern timeline is implemented.",
    )
    APP.write_text(text, encoding="utf-8")

    cfg = CONFIG.read_text(encoding="utf-8")
    if '__version__ = "2.0.0"' in cfg:
        cfg = cfg.replace('__version__ = "2.0.0"', '__version__ = "2.1.0"', 1)
        CONFIG.write_text(cfg, encoding="utf-8")
        print("[apply] version -> 2.1.0")
    else:
        print("[ok] version marker not changed (already updated or customized)")

    print("\nProduction hardening patch applied. Run: python -m compileall -q market_forecaster && pytest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
