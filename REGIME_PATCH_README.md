# Regime Patch 2.3.1 Repair

This repair fixes the 2.3.0 installer bug that skipped payload copying when the ZIP was extracted directly into the repository root.

# Market Forecaster 2.3.0 — Volatility + Regime Engine

This overlay assumes the 2.2.0 Validation Lab and 2.2.1 forecast-display hotfix are already applied.

## What this adds

- A causal market-regime engine with five composite states: `TREND_UP`, `TREND_DOWN`, `RANGE`, `HIGH_VOL`, and `STRESS`.
- Separate trend and volatility states plus 20D/60D realized volatility, volatility percentile, ATR/price, 5D/20D returns, and rolling drawdown.
- A daily-bar HAR-inspired Ridge volatility model forecasting 1, 5, and 20-session annualized volatility.
- Regime labels on every Production Model Zoo fold, calculated from the **training window only**.
- Validation-driven regime routing. Only models that already pass the global production gate are eligible.
- Exact composite-regime evidence is preferred; volatility-state matching is the only fallback.
- A routing prior is enabled only with at least two matching folds.
- The ensemble combines that routing prior with fresh held-out validation; regime routing never overrides current validation quality.
- A new Volatility + Regime dashboard inside the Ensemble tab.
- Protected API endpoint: `GET /api/v1/regime/{ticker}`.

## Important production behavior

Routing is intentionally conservative. If the Validation Lab has too little matching evidence, the app leaves routing disabled and the ensemble remains validation-weighted only.

The HAR-style volatility model uses daily bars, not intraday realized variance. The UI labels it as a **daily proxy** so it is not presented as institutional intraday HAR-RV.

## Apply

Extract the ZIP into the `market_forecaster_v2` repository root, then run:

```bash
python apply_regime_patch_2_3_1.py
python -m compileall -q market_forecaster
pytest
streamlit run market_forecaster/app.py
```

If your shell is already inside `market_forecaster`:

```bash
python ../apply_regime_patch_2_3_1.py
python -m compileall -q .
pytest tests
streamlit run app.py
```

## Workflow after install

1. Run a forecast.
2. Open **Ensemble** to inspect the current regime and volatility forecasts.
3. Open **Backtest** and run **Production Model Zoo**.
4. If enough same-regime evidence exists and one or more models pass the production gate, the app stores a learned routing prior.
5. Rerun Forecast. The ensemble combines the routing prior with fresh held-out validation weights.

## What comes next

After this stabilizes, the next modeling sprint should add multi-horizon XGBoost/quantile forecasts and then feed richer options information (GEX maturity buckets + IV surface level/skew/term structure) into this regime layer.
