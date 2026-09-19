# Market Forecaster 3.7.0 — Model Tournament

Built against GitHub `master` at **v3.6.0**.

## Scope

3.7 stays inside the refocused Market Forecaster mission:

> **Predict and validate future stock/market prices and returns.**

It does not add brokerage execution, strategy automation, portfolio management, or AI Reporter integration.

## What 3.7 adds

The 3.6 research protocol remains the authority:

```text
Targets: 1D / 5D / 10D / 20D cumulative log return
Features: 3.6-price-volume-v1
Validation: chronological expanding window
Purge: >= forecast horizon
Baseline: zero future return
```

3.7 expands the challenger set without changing that protocol.

### Baselines

```text
zero_return
historical_mean
```

### Linear / classic ML

```text
Ridge
Elastic Net
Random Forest
HistGradientBoosting
```

### Gradient boosting

```text
XGBoost       <- nonlinear reference benchmark
LightGBM      <- optional research dependency
CatBoost      <- optional research dependency
```

### Deep sequence challengers

```text
LSTM
TCN
Transformer
```

The deep models are implemented with PyTorch and are optional.

## Fair comparison rule

All models use the same:

```text
feature schema
target origin dates
training windows
validation windows
horizon embargo
OOS metrics
```

Sequence models use a causal feature lookback ending at the same forecast-origin row. Their imputer and scaler are fit on training rows only. No validation target is used during training.

## Two reference comparisons

3.7 measures each model against:

1. **zero-return baseline** — does the model beat an unchanged-price forecast?
2. **XGBoost reference** — does a new challenger improve on the current strong nonlinear benchmark?

New fields include:

```text
Lift vs Zero %
Zero lift bootstrap CI
Lift vs XGBoost %
Win rate vs XGBoost
XGBoost lift bootstrap CI
```

## Challenger status

```text
REFERENCE                 XGBoost
CHALLENGER_PROMISING      stronger paired OOS evidence vs XGBoost
MIXED_VS_XGB              mean improvement, confidence not strong enough
NO_LIFT_VS_XGB            no mean improvement
NO_XGB_REFERENCE          XGBoost was unavailable/not run
BASELINE                  baseline model
```

`CHALLENGER_PROMISING` requires:

```text
>= 3 completed folds
>= 60 OOS observations
>= 2% lower return MAE than XGBoost
>= 52% directional accuracy
paired-fold 95% lift CI lower bound > 0
```

This is still **research-only**. It cannot promote a production model.

## Tournament ranking

Within each horizon, models receive a descriptive `tournament_rank` based on:

1. return MAE
2. return RMSE as tie-breaker

The UI shows the lowest-OOS-MAE model for each horizon. This is not a production selection rule.

## Optional research dependencies

The normal production requirements are **not modified**.

To enable all challengers on a research workstation:

```powershell
pip install -r market_forecaster\requirements-research-models.txt
```

That optional file contains LightGBM, CatBoost and PyTorch.

If they are not installed, Market Forecaster simply reports those models unavailable and continues with the installed models.

## UI presets

The 3.7 Research Lab offers:

```text
Fast core       baseline + existing core models
Full tabular    all installed non-deep models
Deep research   all installed models including LSTM/TCN/Transformer
```

Deep research is intentionally not the default because every neural challenger is retrained inside every walk-forward fold.

## CLI

Fast tournament:

```powershell
python -m market_forecaster.scripts.research_experiment --ticker AAPL --period 5y
```

Full installed tabular set example:

```powershell
python -m market_forecaster.scripts.research_experiment `
  --ticker SPY `
  --period 10y `
  --folds 5 `
  --models zero_return,historical_mean,ridge,elastic_net,random_forest,hist_gradient_boosting,xgboost,lightgbm,catboost
```

Deep example:

```powershell
python -m market_forecaster.scripts.research_experiment `
  --ticker AAPL `
  --period 10y `
  --models zero_return,xgboost,lstm,tcn,transformer `
  --sequence-lookback 20 `
  --deep-epochs 15
```

List model availability:

```powershell
python -m market_forecaster.scripts.research_experiment --ticker SPY --list-models
```

## API

Model availability:

```text
GET /api/v1/research/models
```

Tournament:

```text
GET /api/v1/research/experiment/AAPL?period=5y&models=zero_return,xgboost,lightgbm&n_splits=5&test_size=20
```

## Install

Extract the patch under the repository root and keep the directory intact.

```powershell
python market_forecaster_v2_model_tournament_patch_3.7.0\apply_model_tournament_patch_3_7_0.py
python -m compileall -q market_forecaster
python -m pytest market_forecaster\tests\test_model_tournament.py market_forecaster\tests\test_tournament_runner.py -q
streamlit run market_forecaster\app.py
```

The installer uses only the script-relative `mf37_payload_v370` directory.

## Recommended next milestone — 3.8

**Feature Intelligence / Ablation Lab.**

Keep the 3.7 tournament fixed, then add candidate feature families independently:

```text
market/sector context
VIX and volatility regime
rates and yield-curve state
credit spreads
US dollar / commodities
relative strength / beta
options implied volatility
options skew
options term structure
options pressure / gamma proxy
```

A feature family stays only if it produces repeatable OOS improvement across multiple tickers/horizons.
