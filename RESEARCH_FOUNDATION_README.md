# Market Forecaster 3.6.0 — Research & Forecasting Foundation

Built against GitHub `master` at **v3.5.0**.

## Scope reset

Market Forecaster remains focused on **predicting and validating future stock/market prices**.

AI Reporter remains a separate project. No AI Reporter dependency is introduced in 3.6.

The existing Decision Layer, Opportunity Ranking and Portfolio overlay remain available as downstream consumers, but 3.6 adds no new trading/execution functionality.

## Canonical research target

Primary model target:

```text
r[t,h] = log(Close[t+h] / Close[t])
```

for:

```text
1D / 5D / 10D / 20D
```

Projected price remains an output:

```text
Projected Price = Current Price * exp(predicted_log_return)
```

## New research foundation

```text
core/
├── targets.py
├── feature_store.py
└── experiment_runner.py
```

`targets.py` creates future log return, simple return, direction, target price and explicit target-end timestamp for every horizon.

`feature_store.py` creates a versioned point-in-time causal dataset. 3.6 deliberately starts with price, volume, trend, realized volatility, downside volatility, gap/intrabar state and calendar state.

`experiment_runner.py` evaluates all models on identical chronological folds.

Initial contestants:

```text
zero_return
historical_mean
Ridge
Random Forest
XGBoost
```

The zero-return forecast is mandatory.

## Leakage controls

For horizon `h`:

```text
purge_gap = max(user_embargo, h)
```

The runner also verifies the actual end timestamp of the last training target. If a training target reaches the validation window, the experiment fails.

No random train/test splits are allowed.

## Research metrics

Per model and horizon:

```text
Return MAE (bps)
Return RMSE (bps)
Directional accuracy
Reconstructed price sMAPE
MAE lift vs zero-return
Fold win rate vs zero-return
Paired-fold bootstrap lift interval
OOS observation count
```

## Research statuses

```text
BASELINE
RESEARCH
MIXED
NO_LIFT
PROMISING
```

`PROMISING` currently requires all of:

```text
>=3 completed folds
>=60 OOS observations
>=2% return-MAE improvement vs zero-return
>=52% directional accuracy
paired-fold lift 95% CI lower bound > 0
```

This is **research evidence only**. It cannot promote a production model.

## Forecast Research Lab

Backtest gains a new:

```text
🧪 Forecast Research Lab — 3.6
```

This runs the 1D/5D/10D/20D experiment for the selected ticker.

## CLI

```powershell
python -m market_forecaster.scripts.research_experiment --ticker AAPL --period 5y
```

## API

Protected:

```text
GET /api/v1/research/experiment/AAPL?period=5y&n_splits=5&test_size=20
```

## Install

From the repo root:

```powershell
python market_forecaster_v2_research_foundation_patch_3.6.0\apply_research_foundation_patch_3_6_0.py
python -m compileall -q market_forecaster
python -m pytest market_forecaster\tests\test_research_targets.py market_forecaster\tests\test_feature_store.py market_forecaster\tests\test_experiment_runner.py -q
streamlit run market_forecaster\app.py
```

## Recommended next development

**3.7 — Model Tournament:** add LightGBM, CatBoost, TCN, LSTM/GRU and one modern time-series Transformer challenger through this exact 3.6 protocol.

**3.8 — Feature Intelligence / Ablation Lab:** add market/sector context, VIX/rates/credit/dollar, options IV/skew/term structure/GEX/flow, and other feature families one at a time; retain them only if they create repeatable OOS lift.

**3.9 — Calibration & Adaptive Uncertainty:** calibrate P(up) and compare rolling/adaptive conformal methods using only prior OOS residuals.

AI Reporter remains outside this roadmap until that project is independently ready.
