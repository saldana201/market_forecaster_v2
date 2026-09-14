# Market Forecaster 2.8.0 — Adaptive Options Promotion

Built against GitHub `master` after the v2.7 commit.

## Purpose

v2.7 established whether real observed options features can beat a zero-return
baseline out of sample. v2.8 is the controlled promotion layer.

A historical PASS alone is **not** enough. Before options can influence the
production path:

1. The v2.7 horizon gate must be `PASS`.
2. The **latest OOS fold must still beat baseline**.
3. The current Options Flow snapshot must have at least 60% usable feature
   coverage.
4. A current options Ridge forecast is trained only on historical observations
   whose future outcome is already known.
5. The predicted return is clipped to the historical 2.5–97.5 percentile range
   and an additional hard horizon risk cap.
6. Options influence is capped at **5–15% per promoted horizon**.

If any of these conditions fail, that horizon is automatically demoted and the
pre-options Production Consensus remains unchanged.

## Layer order

The production path is now:

`Validated classic ensemble`
→ `gated XGBoost consensus`
→ `historically validated options overlay`

Options never replace the existing production path.

## Automatic demotion

A horizon is immediately held out of production if its newest OOS validation
fold no longer beats the zero-return baseline. This gives the system an
evidence-based way to stop using options features when their edge degrades.

## Current proxies remain proxies

The v2.6 fields are still labeled appropriately:
- GEX = signed open-interest/Greek proxy, not known dealer inventory.
- Directional pressure = quote-side proxy, not a true aggressor feed.

v2.8 promotes predictive evidence, not stronger claims about the underlying
market microstructure.

## UI

After enough real snapshot history exists:

1. Run a normal forecast with **Options Flow** and **Ensemble** enabled.
2. Run XGBoost if desired. XGBoost is no longer required for the consensus panel.
3. Open **Ensemble → Production Consensus**.
4. Promoted options anchors appear as amber triangles.
5. The pre-options consensus remains visible for comparison whenever options are active.

Because v2.7 requires at least 60 unique market sessions, the options production
layer will remain in `COLLECTING` or `HOLD` until sufficient real evidence exists.

## API

Protected endpoint:

`GET /api/v1/options-promotion/{ticker}?period=2y`

The API uses the latest persisted real options snapshot as its current input.

## Install

Extract this patch folder directly under the `market_forecaster_v2` repo root.

From the repo root:

```bash
python market_forecaster_v2_options_promotion_patch_2.8.0/apply_options_promotion_patch_2_8_0.py
python -m compileall -q market_forecaster
pytest market_forecaster/tests/test_options_promotion.py -q
streamlit run market_forecaster/app.py
```

If already inside `market_forecaster/`:

```bash
python ../market_forecaster_v2_options_promotion_patch_2.8.0/apply_options_promotion_patch_2_8_0.py
python -m compileall -q .
pytest tests/test_options_promotion.py -q
streamlit run app.py
```

## Next milestone

Recommended 2.9: persistent forecast-run audit history and champion/challenger
model governance. Every production forecast should record the model versions,
gates, weights, regime, data freshness, options evidence, output path, and later
realized outcome so model drift and promotion/demotion decisions can be audited.
