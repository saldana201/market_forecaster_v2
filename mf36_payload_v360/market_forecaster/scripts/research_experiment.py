"""Run the v3.6 research experiment from the command line."""
from __future__ import annotations
import argparse,json
from market_forecaster.core.data import fetch_stock_data
from market_forecaster.core.feature_store import build_feature_store
from market_forecaster.core.experiment_runner import run_research_experiment

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--ticker",required=True)
    parser.add_argument("--period",default="5y")
    parser.add_argument("--folds",type=int,default=5)
    parser.add_argument("--test-size",type=int,default=20)
    parser.add_argument("--models",default="zero_return,historical_mean,ridge,random_forest,xgboost")
    args=parser.parse_args()
    ticker=args.ticker.upper().strip()
    frame=fetch_stock_data(ticker,args.period,"1d")
    if frame.empty: raise SystemExit(f"No data available for {ticker}")
    features,metadata=build_feature_store(frame,ticker)
    result=run_research_experiment(
        features,models=[x.strip() for x in args.models.split(",") if x.strip()],
        n_splits=args.folds,test_size=args.test_size
    )
    result["ticker"]=ticker
    result["dataset_metadata"]=metadata.to_dict()
    print(json.dumps(result,indent=2,default=str))

if __name__=="__main__":
    main()
