# Market Forecaster 3.0.1 Repair

Repairs the 3.0 installer payload-collision failure. This repair never reads a generic repo-root `payload/` directory and is safe to run after the partial 3.0 failure.

From the repo root, extract this entire folder and run:

```powershell
python market_forecaster_v2_deployment_policy_repair_3.0.1/apply_deployment_policy_repair_3_0_1.py
python -m compileall -q market_forecaster
python -m pytest market_forecaster/tests/test_forecast_audit.py market_forecaster/tests/test_deployment_policy.py -q
streamlit run market_forecaster/app.py
```

Do **not** run the old `apply_deployment_policy_patch_3_0_0.py` again.
