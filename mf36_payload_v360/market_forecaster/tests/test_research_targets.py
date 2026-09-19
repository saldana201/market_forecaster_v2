from __future__ import annotations
import numpy as np
import pandas as pd
from market_forecaster.core.targets import add_forward_return_targets,reconstruct_price

def _frame(n=40):
    return pd.DataFrame({
        "Date":pd.bdate_range("2026-01-01",periods=n),
        "Open":np.arange(n)+99.0,"High":np.arange(n)+102.0,
        "Low":np.arange(n)+98.0,"Close":np.arange(n)+100.0,
        "Volume":np.arange(n)+1000.0,
    })

def test_forward_log_return_matches_definition():
    out=add_forward_return_targets(_frame(),horizons=[5])
    expected=np.log(out.loc[5,"Close"]/out.loc[0,"Close"])
    assert np.isclose(out.loc[0,"target_log_return_5d"],expected)

def test_target_end_date_is_horizon_session_not_calendar_day():
    out=add_forward_return_targets(_frame(),horizons=[5])
    assert out.loc[0,"target_end_date_5d"]==out.loc[5,"Date"]

def test_price_reconstruction_roundtrip():
    out=add_forward_return_targets(_frame(),horizons=[10])
    price=reconstruct_price(out.loc[0,"Close"],out.loc[0,"target_log_return_10d"])
    assert np.isclose(price,out.loc[10,"Close"])
