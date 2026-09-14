# Market Forecaster 2.7.0 — Historical Options Intelligence

Built against GitHub `master` after the v2.6 commit.

## Purpose

Options Flow v2 started persisting real observed option-chain snapshots. 2.7 turns that history into a guarded validation dataset.

This release does **not** make historical options data up and it does **not** immediately alter Regime routing or Production Consensus.

## Validation protocol

For each ticker:

1. Keep only the latest real snapshot per New York market session.
2. Require at least **60 unique sessions** before validation is armed.
3. Align a snapshot to the **next market-session open**.
4. Measure cumulative return from that open to the close of the 1st, 5th, 10th, and 20th future sessions.
5. Use expanding walk-forward folds with a horizon-sized embargo.
6. Compare a Ridge model using options features against a mandatory **zero-return baseline**.
7. A horizon receives PASS only when all of the following hold:
   - >=3 completed OOS folds
   - >=3% lower MAE than baseline
   - >=52% directional accuracy
   - beats baseline on >=60% of folds
   - >=15 OOS predictions

A PASS is a **research promotion candidate only** in 2.7.

## Features tested

- Options signal score
- Directional quote-side pressure proxy
- Pressure coverage
- Gamma balance proxy
- ATM IV
- 25-delta skew
- IV term-structure slope
- Put/call volume and OI ratios
- 0–7D pressure/skew/gamma balance
- 8–30D pressure/skew/gamma balance

## UI

After you have real snapshot history:

**Backtest → Historical Options Intelligence → Run Historical Options Validation**

The panel shows snapshot readiness, 1D/5D/10D/20D gates, model-vs-baseline MAE, directional accuracy, fold win rate, and descriptive feature rank IC.

## API

Protected endpoint:

`GET /api/v1/options-history/{ticker}?period=2y`

## Install

Extract this patch folder directly under the `market_forecaster_v2` repo root.

From the repo root:

```bash
python market_forecaster_v2_options_history_patch_2.7.0/apply_options_history_patch_2_7_0.py
python -m compileall -q market_forecaster
pytest market_forecaster/tests/test_historical_options.py -q
streamlit run market_forecaster/app.py
```

If you are already inside the inner `market_forecaster` folder:

```bash
python ../market_forecaster_v2_options_history_patch_2.7.0/apply_options_history_patch_2_7_0.py
python -m compileall -q .
pytest tests/test_historical_options.py -q
streamlit run app.py
```

## Important

The current v2.6 GEX and directional-pressure values remain explicitly **proxies**. 2.7 tests whether those observed proxies have predictive value; it does not relabel them as true dealer inventory or true aggressor flow.

## Next milestone

2.8 should promote only repeatedly validated PASS horizons into the regime/consensus layer, with capped weights and automatic demotion when rolling OOS evidence deteriorates.
