# Market Forecaster 3.8.0 — Feature Intelligence / Ablation Lab

Built against GitHub `master` at **v3.7.0**.

## Purpose

3.7 answered:

> Which model predicts future returns best under one common protocol?

3.8 asks:

> Which additional information actually improves those forecasts out of sample?

The model tournament is held fixed. Feature families must earn their place through controlled ablations.

## Initial feature families

3.8 uses only context that can be aligned causally through the existing daily market-data layer:

```text
broad_market
  SPY
  QQQ

volatility
  ^VIX

rates
  ^TNX

credit
  HYG
  LQD
  HYG-minus-LQD return spread

dollar
  DX-Y.NYB

sector (optional)
  user-supplied ETF such as XLK, XLF, XLE, XLV
```

No current news snapshot and no current options-chain snapshot are backfilled into historical rows.

## Point-in-time alignment

The daily feature store already assumes a forecast is issued after `Close[t]`.

External series therefore may use a same-day close at `t`.

If a context market did not trade on the target date, 3.8 uses:

```text
most recent source observation <= target date
```

with a bounded staleness window.

It never uses the next future source observation.

Each aligned source also receives an `age_days` feature.

## Source features

For market/ETF-style sources:

```text
1-session log return
5-session log return
20-session log return
20-session realized volatility
distance from 20-session SMA
source age
```

For level-style series such as VIX and ^TNX:

```text
current level
1-session change
5-session change
20-session change
20-session z-score
source age
```

## Ablation contract

For each requested family:

```text
BASE:
3.6 price/volume feature set

VERSUS:

BASE + one context family
```

Everything else stays fixed:

```text
same target
same ticker history
same model
same horizon
same train window
same purge/embargo
same test window
same OOS observations
```

If the fold/date signature differs, 3.8 returns:

```text
PROTOCOL_MISMATCH
```

and refuses to report feature lift.

## Evidence labels

Each family/model/horizon comparison is labeled:

```text
SUPPORTED
MIXED
NO_LIFT
```

`SUPPORTED` currently requires:

```text
>= 3 folds
>= 60 OOS observations
>= 2% MAE improvement vs the same model without the family
paired-fold 95% lift CI lower bound > 0
directional accuracy cannot deteriorate by more than 1 percentage point
```

Family-level summaries are:

```text
EVIDENCE_FOUND
MIXED
NO_LIFT
UNAVAILABLE
PROTOCOL_MISMATCH
```

These are research labels only. They do not modify production deployment.

## Recommended ablation models

Default:

```text
Ridge
HistGradientBoosting
XGBoost
```

This gives one linear model and two nonlinear models while keeping runtime practical.

The UI also supports:

```text
XGBoost focused
Core ablation
Full tabular
```

Sequence/deep models remain available in the 3.7 Model Tournament, but are not the default for feature attribution because repeated deep fitting can make ablation experiments unnecessarily expensive and harder to interpret.

## New files

```text
market_forecaster/
├── core/
│   ├── market_context.py
│   └── feature_ablation.py
├── ui/
│   └── feature_ablation_panel.py
├── api/routes/
│   └── feature_ablation.py
├── scripts/
│   └── feature_ablation.py
└── tests/
    ├── test_market_context.py
    └── test_feature_ablation.py
```

## UI

Backtest now contains:

```text
Model Tournament — 3.7
Feature Intelligence & Ablation — 3.8
```

## CLI

Default feature ablation:

```powershell
python -m market_forecaster.scripts.feature_ablation `
  --ticker AAPL `
  --period 5y
```

With an explicit sector reference:

```powershell
python -m market_forecaster.scripts.feature_ablation `
  --ticker AAPL `
  --period 10y `
  --sector-ticker XLK `
  --families broad_market,volatility,rates,credit,dollar,sector
```

XGBoost-only:

```powershell
python -m market_forecaster.scripts.feature_ablation `
  --ticker SPY `
  --period 10y `
  --models xgboost
```

## API

Protected:

```text
GET /api/v1/research/feature-ablation/AAPL
```

Optional query fields include:

```text
period
families
models
sector_ticker
n_splits
test_size
```

## Install

From the repository root:

```powershell
python market_forecaster_v2_feature_intelligence_patch_3.8.0\apply_feature_intelligence_patch_3_8_0.py

python -m compileall -q market_forecaster

python -m pytest market_forecaster\tests\test_market_context.py market_forecaster\tests\test_feature_ablation.py -q

streamlit run market_forecaster\app.py
```

## Why options and news are not in 3.8 yet

The existing options module can observe the current chain and can accumulate snapshots going forward, but a robust historical IV/skew/term-structure ablation needs a real point-in-time historical dataset.

The same rule applies to news and analyst text.

3.8 will not manufacture historical features from information that was not actually available at the historical forecast timestamp.

## Recommended next milestone

**3.9 — Probability Calibration + Adaptive Uncertainty**

Once 3.8 identifies which information families deserve to remain, 3.9 should turn the best return forecasts into calibrated:

```text
P(up)
return quantiles
price ranges
adaptive conformal intervals
coverage diagnostics
```

using only prior out-of-sample residuals.
