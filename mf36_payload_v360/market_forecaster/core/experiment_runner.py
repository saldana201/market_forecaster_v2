"""Leakage-controlled multi-horizon research experiment runner (v3.6)."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Iterable
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from market_forecaster.core.feature_store import assert_point_in_time_integrity, research_feature_columns
from market_forecaster.core.targets import DEFAULT_RESEARCH_HORIZONS, target_columns
from market_forecaster.core.validation import expanding_window_splits, paired_fold_improvement

try:
    from xgboost import XGBRegressor
    XGBOOST_RESEARCH_AVAILABLE = True
except ImportError:
    XGBRegressor = None
    XGBOOST_RESEARCH_AVAILABLE = False

DEFAULT_MODELS = ("zero_return", "historical_mean", "ridge", "random_forest", "xgboost")

@dataclass(frozen=True)
class FoldResult:
    horizon: int
    fold: int
    model: str
    train_rows: int
    test_rows: int
    train_last_date: str
    test_first_date: str
    return_mae_bps: float
    return_rmse_bps: float
    directional_accuracy_pct: float
    price_smape_pct: float
    def to_dict(self): return asdict(self)

@dataclass
class ModelHorizonResult:
    horizon: int
    model: str
    folds_run: int
    observations: int
    return_mae_bps: float
    return_rmse_bps: float
    directional_accuracy_pct: float
    price_smape_pct: float
    improvement_vs_zero_mae_pct: float
    fold_win_rate_vs_zero_pct: float
    improvement_ci_low_pct: float
    improvement_ci_high_pct: float
    research_status: str
    notes: list[str]
    def to_dict(self): return asdict(self)

def _smape(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    denom = (np.abs(actual)+np.abs(predicted))/2.0
    good = np.isfinite(actual)&np.isfinite(predicted)&(denom>0)
    if not good.any(): return float("nan")
    return float(np.mean(np.abs(actual[good]-predicted[good])/denom[good])*100.0)

def _point_metrics(y_true, y_pred, anchors):
    y_true = np.asarray(y_true,dtype=float)
    y_pred = np.asarray(y_pred,dtype=float)
    anchors = np.asarray(anchors,dtype=float)
    valid = np.isfinite(y_true)&np.isfinite(y_pred)&np.isfinite(anchors)&(anchors>0)
    y_true,y_pred,anchors = y_true[valid],y_pred[valid],anchors[valid]
    if not len(y_true):
        return {"mae_bps":np.nan,"rmse_bps":np.nan,"direction":np.nan,"price_smape":np.nan}
    err = y_true-y_pred
    return {
        "mae_bps":float(np.mean(np.abs(err))*10000.0),
        "rmse_bps":float(np.sqrt(np.mean(err**2))*10000.0),
        "direction":float(np.mean(np.sign(y_true)==np.sign(y_pred))*100.0),
        "price_smape":_smape(anchors*np.exp(y_true),anchors*np.exp(y_pred)),
    }

def _build_model(name, random_state):
    if name=="ridge":
        return Pipeline([
            ("impute",SimpleImputer(strategy="median")),
            ("scale",StandardScaler()),
            ("model",Ridge(alpha=3.0)),
        ])
    if name=="random_forest":
        return Pipeline([
            ("impute",SimpleImputer(strategy="median")),
            ("model",RandomForestRegressor(n_estimators=200,max_depth=8,min_samples_leaf=5,max_features=0.75,n_jobs=1,random_state=random_state)),
        ])
    if name=="xgboost":
        if not XGBOOST_RESEARCH_AVAILABLE: return None
        return XGBRegressor(
            objective="reg:squarederror",n_estimators=300,max_depth=4,learning_rate=0.035,
            min_child_weight=5,subsample=0.82,colsample_bytree=0.82,reg_alpha=0.05,
            reg_lambda=2.0,tree_method="hist",n_jobs=1,random_state=random_state,verbosity=0
        )
    return None

def _validate_no_label_overlap(frame,horizon,train_end_exclusive,test_start):
    cols = target_columns(horizon)
    if train_end_exclusive<=0 or test_start>=len(frame): return
    train_target_end = pd.to_datetime(frame.iloc[train_end_exclusive-1][cols["end_date"]],errors="coerce")
    test_start_date = pd.to_datetime(frame.iloc[test_start]["Date"],errors="coerce")
    if pd.notna(train_target_end) and pd.notna(test_start_date) and train_target_end>=test_start_date:
        raise RuntimeError(
            f"Target overlap detected for {horizon}D: last train label ends {train_target_end}, test starts {test_start_date}"
        )

def run_research_experiment(
    feature_frame: pd.DataFrame,
    *,
    horizons: Iterable[int]=DEFAULT_RESEARCH_HORIZONS,
    models: Iterable[str]=DEFAULT_MODELS,
    n_splits: int=5,
    test_size: int=20,
    min_train_size: int=180,
    embargo: int=0,
    random_state: int=42,
) -> dict:
    pit = assert_point_in_time_integrity(feature_frame)
    if pit["status"]!="PASS":
        raise ValueError(f"Point-in-time integrity failed: {pit['problems']}")
    features = research_feature_columns(feature_frame)
    if not features: raise ValueError("No research features are available")

    requested_models=[]
    for name in models:
        name=str(name).strip().lower()
        if name and name not in requested_models: requested_models.append(name)

    fold_rows=[]
    unavailable=[]
    for horizon in sorted({int(h) for h in horizons if int(h)>0}):
        cols=target_columns(horizon)
        if cols["log_return"] not in feature_frame.columns or cols["end_date"] not in feature_frame.columns:
            continue
        work=feature_frame[["Date","Close",cols["log_return"],cols["end_date"],*features]].copy()
        work=work.dropna(subset=["Date","Close",cols["log_return"],cols["end_date"]]).reset_index(drop=True)
        if len(work)<max(min_train_size+test_size+horizon,60): continue

        X=work[features].replace([np.inf,-np.inf],np.nan)
        y=pd.to_numeric(work[cols["log_return"]],errors="coerce")
        anchors=pd.to_numeric(work["Close"],errors="coerce")
        purge_gap=max(int(embargo),int(horizon))
        splits=list(expanding_window_splits(
            len(work),test_size=int(test_size),n_splits=int(n_splits),gap=purge_gap,
            min_train_size=max(int(min_train_size),8*horizon)
        ))
        for split in splits:
            _validate_no_label_overlap(work,horizon,split.train_end,split.test_start)
            X_train=X.iloc[split.train_start:split.train_end]
            y_train=y.iloc[split.train_start:split.train_end]
            X_test=X.iloc[split.test_start:split.test_end]
            y_test=y.iloc[split.test_start:split.test_end].to_numpy(dtype=float)
            anchor_test=anchors.iloc[split.test_start:split.test_end].to_numpy(dtype=float)
            train_last_date=pd.Timestamp(work.iloc[split.train_end-1]["Date"]).isoformat()
            test_first_date=pd.Timestamp(work.iloc[split.test_start]["Date"]).isoformat()

            for model_name in requested_models:
                if model_name=="zero_return":
                    pred=np.zeros(len(X_test),dtype=float)
                elif model_name=="historical_mean":
                    pred=np.full(len(X_test),float(np.nanmean(y_train.to_numpy(dtype=float))),dtype=float)
                else:
                    model=_build_model(model_name,random_state+split.fold+horizon)
                    if model is None:
                        if model_name not in unavailable: unavailable.append(model_name)
                        continue
                    model.fit(X_train,y_train)
                    pred=np.asarray(model.predict(X_test),dtype=float)
                metrics=_point_metrics(y_test,pred,anchor_test)
                fold_rows.append(FoldResult(
                    horizon=horizon,fold=split.fold,model=model_name,train_rows=len(X_train),test_rows=len(X_test),
                    train_last_date=train_last_date,test_first_date=test_first_date,
                    return_mae_bps=metrics["mae_bps"],return_rmse_bps=metrics["rmse_bps"],
                    directional_accuracy_pct=metrics["direction"],price_smape_pct=metrics["price_smape"]
                ).to_dict())

    folds_df=pd.DataFrame(fold_rows)
    summaries=[]
    if not folds_df.empty:
        for (horizon,model),group in folds_df.groupby(["horizon","model"],sort=True):
            zero=folds_df[(folds_df["horizon"]==horizon)&(folds_df["model"]=="zero_return")][["fold","return_mae_bps"]].rename(columns={"return_mae_bps":"zero_mae"})
            paired=group[["fold","return_mae_bps"]].merge(zero,on="fold",how="inner")
            improvement=win_rate=ci_low=ci_high=float("nan")
            if model!="zero_return" and not paired.empty:
                base=float(paired["zero_mae"].mean())
                cand=float(paired["return_mae_bps"].mean())
                if base>0: improvement=(base-cand)/base*100.0
                win_rate=float((paired["return_mae_bps"]<paired["zero_mae"]).mean()*100.0)
                evidence=paired_fold_improvement(
                    paired["return_mae_bps"].to_numpy(),paired["zero_mae"].to_numpy(),seed=random_state+int(horizon)
                )
                ci_low=evidence["ci_low_pct"]; ci_high=evidence["ci_high_pct"]

            direction=float(group["directional_accuracy_pct"].mean())
            folds_run=int(group["fold"].nunique())
            observations=int(group["test_rows"].sum())
            status="BASELINE" if model=="zero_return" else "RESEARCH"
            notes=[]
            if model!="zero_return":
                if folds_run>=3 and observations>=60 and np.isfinite(improvement) and improvement>=2.0 and np.isfinite(direction) and direction>=52.0 and np.isfinite(ci_low) and ci_low>0.0:
                    status="PROMISING"; notes.append("Positive paired-fold improvement CI; eligible for deeper research only.")
                elif np.isfinite(improvement) and improvement>0:
                    status="MIXED"; notes.append("Some OOS improvement, but research evidence is not yet strong.")
                else:
                    status="NO_LIFT"; notes.append("Did not improve the zero-return baseline on current OOS folds.")

            summaries.append(ModelHorizonResult(
                horizon=int(horizon),model=str(model),folds_run=folds_run,observations=observations,
                return_mae_bps=float(group["return_mae_bps"].mean()),
                return_rmse_bps=float(group["return_rmse_bps"].mean()),
                directional_accuracy_pct=direction,
                price_smape_pct=float(group["price_smape_pct"].mean()),
                improvement_vs_zero_mae_pct=improvement,
                fold_win_rate_vs_zero_pct=win_rate,
                improvement_ci_low_pct=ci_low,
                improvement_ci_high_pct=ci_high,
                research_status=status,notes=notes
            ).to_dict())

    return {
        "protocol_version":"3.6-research-v1",
        "feature_schema_version":pit.get("schema_version"),
        "features":features,
        "feature_count":len(features),
        "horizons":sorted({int(h) for h in horizons if int(h)>0}),
        "models_requested":requested_models,
        "models_unavailable":unavailable,
        "n_splits_requested":int(n_splits),
        "test_size":int(test_size),
        "minimum_train_size":int(min_train_size),
        "embargo_rule":"max(user_embargo, horizon)",
        "summaries":summaries,
        "folds":fold_rows,
        "notes":[
            "Research-only: results do not alter champion, deployment, consensus, ranking, or portfolio state.",
            "Every candidate uses the same chronological folds and feature matrix.",
            "Zero future return is the mandatory baseline.",
            "Targets are cumulative log returns; displayed prices can be reconstructed from current price.",
            "PROMISING is a research label only, not a production promotion.",
        ],
    }
