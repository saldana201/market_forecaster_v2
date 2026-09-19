from __future__ import annotations
import numpy as np
import pandas as pd
from market_forecaster.core.feature_store import build_feature_store
from market_forecaster.core.experiment_runner import run_research_experiment

def _frame(n=520):
    rng=np.random.default_rng(7)
    r=np.zeros(n); shocks=rng.normal(0,0.008,n)
    for i in range(1,n): r[i]=0.30*r[i-1]+shocks[i]
    close=100*np.exp(np.cumsum(r))
    return pd.DataFrame({
        "Date":pd.bdate_range("2024-01-01",periods=n),
        "Open":close*(1+rng.normal(0,0.001,n)),
        "High":close*1.01,"Low":close*0.99,"Close":close,
        "Volume":rng.integers(500_000,3_000_000,n),
    })

def test_same_fold_protocol_and_horizon_embargo():
    features,_=build_feature_store(_frame(),"TEST")
    result=run_research_experiment(features,horizons=[1,5,10,20],models=["zero_return","ridge"],n_splits=3,test_size=15,min_train_size=180)
    assert result["embargo_rule"]=="max(user_embargo, horizon)"
    assert result["summaries"]
    assert {x["horizon"] for x in result["summaries"]}=={1,5,10,20}

def test_no_train_label_overlaps_validation_start():
    features,_=build_feature_store(_frame(),"TEST")
    result=run_research_experiment(features,horizons=[20],models=["zero_return"],n_splits=3,test_size=15,min_train_size=180)
    assert result["folds"]
    for row in result["folds"]:
        assert pd.Timestamp(row["train_last_date"])<pd.Timestamp(row["test_first_date"])

def test_research_runner_never_claims_production_promotion():
    features,_=build_feature_store(_frame(),"TEST")
    result=run_research_experiment(features,horizons=[5],models=["zero_return","ridge"],n_splits=3,test_size=15,min_train_size=180)
    allowed={"BASELINE","RESEARCH","PROMISING","MIXED","NO_LIFT"}
    assert {x["research_status"] for x in result["summaries"]}<=allowed
