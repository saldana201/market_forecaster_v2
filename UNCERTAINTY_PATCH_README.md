# Market Forecaster 3.9.0 — Probability Calibration + Adaptive Uncertainty

Built against GitHub `master` at **v3.8.0**.

## Purpose

3.6 established causal multi-horizon return targets and leakage-safe folds.

3.7 compared model families under one protocol.

3.8 tested which external feature families add incremental OOS lift.

3.9 answers a different question:

> How uncertain should we be about each future-price forecast?

The new layer produces, for every 1D / 5D / 10D / 20D horizon:

```text
point expected return
projected price
calibrated P(up)
80% rolling conformal-style range
90% rolling conformal-style range
calibration quality diagnostics
```

## Prequential calibration

This is the most important design rule in 3.9.

For validation fold `k`:

```text
folds 1 ... k-1
      ↓
calibration history
      ↓
calibrate fold k

fold k outcomes are NOT added until after fold k is evaluated
```

Therefore:

```text
changing fold k outcomes
must not change fold k P(up)
or fold k interval width
```

The unit suite explicitly tests this.

## Probability calibration

The underlying return forecast is not itself a probability.

3.9 learns a post-hoc mapping:

```text
predicted future return
        ↓
training-only standardized logistic calibrator
        ↓
P(actual future return > 0)
```

Only earlier out-of-sample predictions are used to fit this mapping.

If the calibration sample contains only one direction, the engine falls back to a Beta(1,1)-smoothed empirical up rate rather than failing.

Current status labels:

```text
CALIBRATED   >= 60 OOS calibration observations
LOW_SAMPLE   30–59
PROVISIONAL  < 30
```

A status describes sample depth, not a guarantee of accuracy.

## Probability diagnostics

3.9 reports:

```text
Brier Score
Brier Skill vs constant 50%
Expected Calibration Error (ECE)
number of probability-evaluation observations
```

Lower Brier and lower ECE are preferable.

## Rolling conformal-style intervals

For every horizon, 3.9 computes prior OOS absolute residuals:

```text
|actual return - predicted return|
```

and uses a conservative finite-sample quantile to create:

```text
predicted return ± residual quantile
```

for nominal:

```text
80%
90%
```

coverage.

Those return bands are converted into projected prices:

```text
price_low  = current_price * exp(lower_log_return)
price_high = current_price * exp(upper_log_return)
```

## Why "conformal-style" rather than guaranteed conformal

Classical conformal coverage relies on exchangeability assumptions.

Financial returns are nonstationary and regime-dependent.

3.9 therefore uses a rolling, prior-OOS residual window to adapt to recent error behavior and always displays actual empirical coverage:

```text
nominal 80% vs observed coverage
nominal 90% vs observed coverage
average interval width
```

The tool does not claim future coverage is guaranteed.

## Adaptive calibration window

Available research windows:

```text
60 OOS observations
120 OOS observations
250 OOS observations
All OOS history
```

A shorter window adapts faster but has less statistical depth.

A longer window is more stable but can react slowly when market error behavior changes.

Default:

```text
120
```

## Feature-set handling

Default:

```text
3.6 base causal price/volume feature set
```

The 3.9 UI also permits one optional 3.8 context family:

```text
broad_market
volatility
rates
credit
dollar
sector
```

This does **not** automatically promote any 3.8 family. It only lets you examine uncertainty for a feature family that your ablation work suggests is worth testing.

## Forecast models

Any available non-baseline 3.7 tournament model can be calibrated:

```text
Ridge
Elastic Net
Random Forest
HistGradientBoosting
XGBoost
LightGBM          if installed
CatBoost          if installed
LSTM              if installed
TCN               if installed
Transformer       if installed
```

Default:

```text
XGBoost
```

Deep models remain slower because they must be retrained inside each walk-forward fold.

## New UI

Backtest/research flow becomes:

```text
Model Tournament — 3.7
        ↓
Feature Intelligence & Ablation — 3.8
        ↓
Probability Calibration & Adaptive Uncertainty — 3.9
```

The current forecast table shows:

```text
Horizon
Target Date
Current Price
Expected Return %
Projected Price
P(up) %
Calibration Status
OOS Calibration Samples
80% Price Low / High
90% Price Low / High
```

A second table reports prequential calibration diagnostics.

## New API

Protected endpoint:

```text
GET /api/v1/research/uncertainty/AAPL
```

Useful query fields:

```text
period=10y
model=xgboost
context_family=volatility
sector_ticker=XLK
n_splits=6
test_size=20
calibration_window=120
```

Use:

```text
calibration_window=0
```

for all OOS history.

## CLI

Base XGBoost calibration:

```powershell
python -m market_forecaster.scripts.uncertainty_research `
  --ticker AAPL `
  --period 10y `
  --model xgboost
```

With VIX context:

```powershell
python -m market_forecaster.scripts.uncertainty_research `
  --ticker AAPL `
  --period 10y `
  --model xgboost `
  --context-family volatility `
  --calibration-window 120
```

Deep model example:

```powershell
python -m market_forecaster.scripts.uncertainty_research `
  --ticker AAPL `
  --period 10y `
  --model tcn `
  --folds 6 `
  --sequence-lookback 20 `
  --deep-epochs 15
```

## New files

```text
market_forecaster/
├── core/
│   └── uncertainty_calibration.py
├── ui/
│   └── uncertainty_panel.py
├── api/routes/
│   └── uncertainty.py
├── scripts/
│   └── uncertainty_research.py
└── tests/
    └── test_uncertainty_calibration.py
```

## Install

From repo root:

```powershell
python market_forecaster_v2_uncertainty_patch_3.9.0\apply_uncertainty_patch_3_9_0.py

python -m compileall -q market_forecaster

python -m pytest market_forecaster\tests\test_uncertainty_calibration.py -q

streamlit run market_forecaster\app.py
```

## Scope boundary

3.9 remains forecasting research.

It does not:

```text
place orders
size positions
change portfolio state
change opportunity rankings
change deployment champion
change production consensus
```

## Recommended next milestone

**4.0 — Forecast Intelligence Platform**

Before calling 4.0 complete, the recommended focus is consolidation rather than another isolated model:

```text
horizon-specific forecast authority
supported feature-family registry
calibrated probability + uncertainty output
cross-ticker validation
persistent research snapshots
single downstream Forecast Contract API
```

The downstream trading engine can then consume a clean forecast contract without Market Forecaster becoming a trading engine itself.
