import json
import pandas as pd
from market_forecaster.core import data_providers as dp

def _frame(provider="fake",periods=30,price=100.0):
    d=pd.bdate_range("2026-01-01",periods=periods); f=pd.DataFrame({"Date":d,"Open":[price]*periods,"High":[price+2]*periods,"Low":[price-2]*periods,"Close":[price+1]*periods,"Volume":[1000]*periods}); f.attrs.update(provider=provider,last_market_timestamp=d[-1].isoformat(),fetched_at_utc="2026-01-31T00:00:00+00:00"); return f

def test_quality_rejects_bad_ohlc():
    f=_frame(); f["High"]=50; r=dp.evaluate_market_frame(f,"bad"); assert r.status=="FAIL"

def test_primary_selected_and_cached(tmp_path,monkeypatch):
    monkeypatch.setenv("MARKET_FORECASTER_DATA_CACHE_DIR",str(tmp_path)); monkeypatch.setattr(dp,"_PROVIDER_FETCHERS",{"primary":lambda *a,**k:_frame("primary"),"secondary":lambda *a,**k:_frame("secondary")})
    out=dp.fetch_market_data_with_failover("SPY",provider_names=["primary","secondary"]); assert out.attrs["provider"]=="primary" and not out.attrs["provider_failover_used"] and list(tmp_path.glob("*.csv"))

def test_secondary_activates_after_primary_failure(tmp_path,monkeypatch):
    monkeypatch.setenv("MARKET_FORECASTER_DATA_CACHE_DIR",str(tmp_path))
    def fail(*a,**k): raise RuntimeError("down")
    monkeypatch.setattr(dp,"_PROVIDER_FETCHERS",{"primary":fail,"secondary":lambda *a,**k:_frame("secondary")})
    out=dp.fetch_market_data_with_failover("SPY",provider_names=["primary","secondary"]); assert out.attrs["provider"]=="secondary" and out.attrs["provider_failover_used"]

def test_cache_fallback(tmp_path,monkeypatch):
    monkeypatch.setenv("MARKET_FORECASTER_DATA_CACHE_DIR",str(tmp_path)); good=_frame("primary"); dp._save_cache(good,"SPY","1y","1d",dp.evaluate_market_frame(good,"primary"))
    def fail(*a,**k): raise RuntimeError("down")
    monkeypatch.setattr(dp,"_PROVIDER_FETCHERS",{"primary":fail}); out=dp.fetch_market_data_with_failover("SPY",provider_names=["primary"]); assert out.attrs["is_cached"] and str(out.attrs["provider"]).startswith("cache:")

def test_stale_cache_rejected(tmp_path,monkeypatch):
    monkeypatch.setenv("MARKET_FORECASTER_DATA_CACHE_DIR",str(tmp_path)); monkeypatch.setenv("MARKET_FORECASTER_DATA_CACHE_MAX_AGE_DAYS","1"); good=_frame("primary"); dp._save_cache(good,"SPY","1y","1d",dp.evaluate_market_frame(good,"primary")); meta=next(tmp_path.glob("*.json")); o=json.loads(meta.read_text()); o["cached_at_utc"]="2020-01-01T00:00:00+00:00"; meta.write_text(json.dumps(o))
    def fail(*a,**k): raise RuntimeError("down")
    monkeypatch.setattr(dp,"_PROVIDER_FETCHERS",{"primary":fail}); assert dp.fetch_market_data_with_failover("SPY",provider_names=["primary"]).empty

def test_comparison_reports_divergence(monkeypatch):
    monkeypatch.setattr(dp,"configured_provider_names",lambda:["a","b"]); monkeypatch.setattr(dp,"_PROVIDER_FETCHERS",{"a":lambda *a,**k:_frame("a",price=100),"b":lambda *a,**k:_frame("b",price=102)}); r=dp.compare_market_data_providers("SPY"); assert r["pairwise"][0]["overlap_rows"]==30 and r["pairwise"][0]["mean_close_diff_pct"]>0
