# Market Forecaster 2.2.0 — Production Validation Lab

This overlay is the next production-hardening step after 2.1.0 / 2.1.1.

## What it adds

- A shared chronological validation module with expanding-window splits and an explicit embargo gap.
- A production Model Zoo comparing **Naive, Prophet, ARIMA, Ridge, and Random Forest on the exact same folds**.
- Mandatory Naive baseline and a conservative promotion gate.
- MAE, RMSE, MAPE, sMAPE, MASE, path directional accuracy, terminal direction accuracy, worst-fold error, and fold stability.
- Paired fold improvement vs Naive with a descriptive bootstrap interval.
- A **Production Validation Lab** inside the existing Backtest tab.
- Auth-protected `GET /api/v1/model-zoo/{ticker}` endpoint.

## Production gate
A non-Naive model is marked PASS only when it:

1. improves mean sMAPE vs Naive by at least 2%,
2. completes every validation fold,
3. beats Naive on at least 60% of paired folds, and
4. averages at least 50% directional accuracy.

A model ranking first is **not** enough to promote it.

## Apply
Recommended: extract this ZIP **into the `market_forecaster_v2` repository root**. The new files will land under `market_forecaster/`. Then run:

```bash
python apply_validation_patch_2_2_0.py
python -m compileall -q market_forecaster   # from repo root
pytest
```

If you prefer to keep the ZIP elsewhere, you can run the script by path while your shell is at the repo root. If you are already inside `market_forecaster`:

```bash
python apply_validation_patch_2_2_0.py
python -m compileall -q .
pytest tests
streamlit run app.py
```

The script backs up modified `app.py`, `api/main.py`, and `config.py` before editing.

## Why LSTM is not in the gate yet
The validation lab intentionally starts with deterministic CPU-friendly baselines. LSTM should be reintroduced only after it can beat those baselines under the same folds, with reproducible training and reasonable runtime.
