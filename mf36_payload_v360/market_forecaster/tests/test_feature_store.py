from __future__ import annotations
import numpy as np
import pandas as pd
from market_forecaster.core.feature_store import build_feature_store,assert_point_in_time_integrity,research_feature_columns

def _frame(n=260):
    rng=np.random.default_rng(123)
    close=100*np.exp(np.cumsum(rng.normal(0.0003,0.01,n)))
    return pd.DataFrame({
        "Date":pd.bdate_range("2025-01-01",periods=n),
        "Open":close*0.999,"High":close*1.01,"Low":close*0.99,
        "Close":close,"Volume":rng.integers(1_000_000,3_000_000,n),
    })

def test_feature_store_passes_structural_pit_integrity():
    out,meta=build_feature_store(_frame(),"TEST")
    check=assert_point_in_time_integrity(out)
    assert check["status"]=="PASS"
    assert meta.schema_version.startswith("3.6")
    assert meta.feature_count>10

def test_future_price_change_cannot_change_past_features():
    base=_frame()
    original,_=build_feature_store(base,"TEST")
    changed=base.copy()
    for col in ["Close","Open","High","Low"]:
        changed.loc[220:,col]*=4.0
    modified,_=build_feature_store(changed,"TEST")
    features=research_feature_columns(original)
    row=200
    for feature in features:
        left=original.loc[row,feature]; right=modified.loc[row,feature]
        if pd.isna(left) and pd.isna(right): continue
        assert np.isclose(left,right,equal_nan=True),feature
