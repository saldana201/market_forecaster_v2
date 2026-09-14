# Market Forecaster Hotfix 2.1.1

Fixes the Trader-mode crash:

`TypeError: '>' not supported between instances of 'str' and 'int'`

## Root cause
`compute_basic_signal()` stored descriptive strings (for example `"bullish"` and `"above SMA20"`) in `SignalResult.components`, while `component_breakdown()` assumed every value was numeric.

## Fix
- Basic-signal component values are now numeric contribution scores.
- The UI breakdown defensively filters unexpected nonnumeric values instead of crashing.
- Existing files are backed up automatically before modification.

## Apply
From either the repository root or the `market_forecaster` directory:

```bash
python apply_hotfix_2_1_1.py
```

Then restart Streamlit. If you are already inside `market_forecaster`:

```bash
streamlit run app.py
```

Optional syntax check:

```bash
python -m compileall -q .
```
