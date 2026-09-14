"""Provider abstraction, quality gates, failover, and last-known-good cache."""
from __future__ import annotations

import io, json, logging, os, re, time, urllib.parse, urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
try:
    import yfinance as yf
except ImportError:  # test/minimal environments
    yf = None

logger = logging.getLogger(__name__)
_REQ = ("Open", "High", "Low", "Close")
_TICKER = re.compile(r"^[A-Z0-9.^=_-]{1,24}$")
_PERIOD_DAYS = {"1mo": 40, "3mo": 120, "6mo": 220, "1y": 400, "2y": 800, "5y": 1900, "10y": 3800}

class ProviderUnavailable(RuntimeError): pass
class ProviderDataError(RuntimeError): pass

@dataclass(frozen=True)
class QualityReport:
    provider: str; status: str; score: float; rows: int
    required_complete_pct: float; ohlc_consistency_pct: float
    positive_close_pct: float; duplicate_dates: int; notes: list[str]
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class ProviderAttempt:
    provider: str; status: str; message: str
    quality_score: float | None = None; rows: int | None = None
    def to_dict(self): return asdict(self)

def normalize_ticker(ticker: str) -> str:
    value = str(ticker or "").upper().strip()
    if not value or not _TICKER.fullmatch(value): raise ValueError("Invalid ticker symbol")
    return value

def configured_provider_names() -> list[str]:
    raw = os.getenv("MARKET_FORECASTER_DATA_PROVIDERS", "yfinance,stooq")
    return [x.strip().lower() for x in raw.split(",") if x.strip()] or ["yfinance", "stooq"]

def _cache_root() -> Path:
    override = os.getenv("MARKET_FORECASTER_DATA_CACHE_DIR")
    return Path(override).expanduser() if override else Path(__file__).resolve().parents[1] / ".local" / "data_cache"

def _cache_enabled() -> bool:
    return os.getenv("MARKET_FORECASTER_DATA_CACHE_ENABLED", "true").lower() not in {"0", "false", "no"}

def _cache_max_age_days() -> int:
    try: return max(1, int(os.getenv("MARKET_FORECASTER_DATA_CACHE_MAX_AGE_DAYS", "7")))
    except Exception: return 7

def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy(); df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df

def canonicalize_market_frame(df: pd.DataFrame, ticker: str, provider: str) -> pd.DataFrame:
    if df is None or df.empty: raise ProviderDataError("provider returned no data")
    out = df.copy()
    if "Date" not in out.columns and "Datetime" not in out.columns: out = out.reset_index()
    out = _flatten(out)
    if "Date" not in out.columns and "Datetime" in out.columns: out = out.rename(columns={"Datetime": "Date"})
    if "Date" not in out.columns: raise ProviderDataError("provider response has no Date/Datetime column")
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce", utc=True).dt.tz_localize(None)
    out = out.dropna(subset=["Date"]).sort_values("Date")
    for col in _REQ:
        if col not in out.columns: raise ProviderDataError(f"provider response missing {col}")
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["Volume"] = pd.to_numeric(out["Volume"], errors="coerce") if "Volume" in out.columns else np.nan
    dup = int(out.duplicated("Date", keep=False).sum())
    out = out.drop_duplicates("Date", keep="last").dropna(subset=["Close"]).reset_index(drop=True)
    if out.empty: raise ProviderDataError("no valid closes")
    out.attrs.update(provider=provider, ticker=ticker, fetched_at_utc=datetime.now(timezone.utc).isoformat(),
                     last_market_timestamp=pd.Timestamp(out["Date"].max()).isoformat(), raw_duplicate_dates=dup)
    return out

def evaluate_market_frame(df: pd.DataFrame, provider="unknown") -> QualityReport:
    if df is None or df.empty: return QualityReport(provider, "FAIL", 0, 0, 0, 0, 0, 0, ["empty frame"])
    if any(c not in df.columns for c in _REQ): return QualityReport(provider, "FAIL", 0, len(df), 0, 0, 0, 0, ["missing OHLC"])
    req = df[list(_REQ)].apply(pd.to_numeric, errors="coerce")
    complete = float(req.notna().all(axis=1).mean()*100)
    positive = float((req.Close > 0).mean()*100)
    consistent = ((req.High >= req.Low) & (req.High >= req[["Open","Close"]].max(axis=1)) & (req.Low <= req[["Open","Close"]].min(axis=1)))
    ohlc = float(consistent.mean()*100)
    dup = int(pd.to_datetime(df["Date"], errors="coerce").duplicated().sum()) if "Date" in df.columns else len(df)
    notes=[]; score=100.0
    if len(df)<2: score-=70; notes.append("fewer than 2 rows")
    elif len(df)<5: score-=20; notes.append("very short history")
    if complete<99: score-=min(30,(100-complete)*2); notes.append("incomplete OHLC")
    if positive<100: score-=min(40,(100-positive)*3); notes.append("non-positive close")
    if ohlc<99: score-=min(40,(100-ohlc)*2); notes.append("OHLC violations")
    if dup: score-=min(10,dup); notes.append("duplicate dates")
    score=float(np.clip(score,0,100))
    status="FAIL" if len(df)<2 or complete<95 or positive<99 or ohlc<95 or score<60 else ("WARN" if score<85 else "PASS")
    return QualityReport(provider,status,score,len(df),complete,ohlc,positive,dup,notes)

def _fetch_yfinance(ticker, period, interval, *, attempts=3, backoff_seconds=.5):
    if yf is None: raise ProviderUnavailable("yfinance is not installed")
    last=None
    for i in range(max(1,attempts)):
        try:
            raw=yf.download(ticker,period=period,interval=interval,auto_adjust=False,progress=False,threads=False)
            return canonicalize_market_frame(raw,ticker,"yfinance")
        except Exception as exc:
            last=exc
            if i+1<attempts: time.sleep(backoff_seconds*(2**i))
    raise ProviderUnavailable(f"yfinance failed: {last}")

def _stooq_symbol(ticker):
    if ticker.endswith("-USD") or ticker.startswith("^") or "=" in ticker: raise ProviderUnavailable("Stooq unsupported for symbol type")
    return ticker.lower()+".us"

def _resample(df, interval):
    if interval=="1d": return df
    rule="W-FRI" if interval=="1wk" else "ME"
    return df.set_index("Date").sort_index().resample(rule).agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}).dropna(subset=["Close"]).reset_index()

def _fetch_stooq(ticker, period, interval):
    if interval not in {"1d","1wk","1mo"}: raise ProviderUnavailable("Stooq interval unsupported")
    end=datetime.now(timezone.utc).date(); start=end-timedelta(days=_PERIOD_DAYS.get(period,400))
    q=urllib.parse.urlencode({"s":_stooq_symbol(ticker),"d1":start.strftime("%Y%m%d"),"d2":end.strftime("%Y%m%d"),"i":"d"})
    req=urllib.request.Request(f"https://stooq.com/q/d/l/?{q}",headers={"User-Agent":"MarketForecaster/3.2"})
    try:
        with urllib.request.urlopen(req,timeout=12) as r: text=r.read().decode("utf-8",errors="replace")
    except Exception as exc: raise ProviderUnavailable(f"Stooq request failed: {exc}") from exc
    if not text.strip() or "No data" in text: raise ProviderUnavailable("Stooq returned no data")
    raw=pd.read_csv(io.StringIO(text))
    daily=canonicalize_market_frame(raw,ticker,"stooq")
    return canonicalize_market_frame(_resample(daily,interval),ticker,"stooq")

_PROVIDER_FETCHERS: dict[str,Callable[...,pd.DataFrame]]={"yfinance":_fetch_yfinance,"stooq":_fetch_stooq}

def _cache_key(ticker,period,interval): return f"{re.sub(r'[^A-Z0-9_-]+','_',ticker.upper())}__{period}__{interval}"

def _save_cache(df,ticker,period,interval,quality):
    if not _cache_enabled(): return
    root=_cache_root(); root.mkdir(parents=True,exist_ok=True); key=_cache_key(ticker,period,interval)
    csv=root/f"{key}.csv"; meta=root/f"{key}.json"; tcsv=root/f"{key}.csv.tmp"; tmeta=root/f"{key}.json.tmp"
    df.to_csv(tcsv,index=False)
    tmeta.write_text(json.dumps({"ticker":ticker,"period":period,"interval":interval,"source_provider":df.attrs.get("provider"),"cached_at_utc":datetime.now(timezone.utc).isoformat(),"last_market_timestamp":df.attrs.get("last_market_timestamp"),"quality":quality.to_dict(),"rows":len(df)},indent=2),encoding="utf-8")
    tcsv.replace(csv); tmeta.replace(meta)

def _load_cache(ticker,period,interval):
    if not _cache_enabled(): raise ProviderUnavailable("cache disabled")
    root=_cache_root(); key=_cache_key(ticker,period,interval); csv=root/f"{key}.csv"; meta=root/f"{key}.json"
    if not csv.exists() or not meta.exists(): raise ProviderUnavailable("no cache")
    obj=json.loads(meta.read_text(encoding="utf-8")); ts=pd.to_datetime(obj.get("cached_at_utc"),errors="coerce",utc=True)
    if pd.isna(ts): raise ProviderUnavailable("invalid cache timestamp")
    age=(pd.Timestamp.now(tz="UTC")-ts).total_seconds()/86400
    if age>_cache_max_age_days(): raise ProviderUnavailable(f"cache too old: {age:.1f}d")
    src=str(obj.get("source_provider") or "unknown"); out=canonicalize_market_frame(pd.read_csv(csv),ticker,f"cache:{src}")
    out.attrs.update(is_cached=True,degraded_data=True,cache_age_days=float(age),cache_source_provider=src,cache_metadata=obj)
    return out

def fetch_market_data_with_failover(ticker,period="1y",interval="1d",*,yfinance_attempts=3,backoff_seconds=.5,provider_names=None):
    symbol=normalize_ticker(ticker); names=provider_names or configured_provider_names(); attempts=[]
    for idx,name in enumerate(names):
        fetcher=_PROVIDER_FETCHERS.get(name)
        if not fetcher: attempts.append(ProviderAttempt(name,"SKIP","unknown provider")); continue
        try:
            frame=fetcher(symbol,period,interval,attempts=yfinance_attempts,backoff_seconds=backoff_seconds) if name=="yfinance" else fetcher(symbol,period,interval)
            q=evaluate_market_frame(frame,name)
            if q.status=="FAIL": attempts.append(ProviderAttempt(name,"REJECT","quality gate failed",q.score,q.rows)); continue
            frame.attrs.update(quality_report=q.to_dict(),data_quality_status=q.status,provider_failover_used=idx>0,is_cached=False,degraded_data=q.status=="WARN")
            attempts.append(ProviderAttempt(name,"ACCEPT",q.status,q.score,q.rows)); frame.attrs["provider_attempts"]=[a.to_dict() for a in attempts]
            _save_cache(frame,symbol,period,interval,q); return frame
        except Exception as exc:
            attempts.append(ProviderAttempt(name,"ERROR",str(exc))); logger.warning("provider failed %s %s",name,type(exc).__name__)
    try:
        frame=_load_cache(symbol,period,interval); q=evaluate_market_frame(frame,frame.attrs.get("provider","cache"))
        if q.status=="FAIL": raise ProviderUnavailable("cache quality failed")
        attempts.append(ProviderAttempt("cache","ACCEPT","last-known-good fallback",q.score,q.rows))
        frame.attrs.update(quality_report=q.to_dict(),data_quality_status=q.status,provider_failover_used=True,provider_attempts=[a.to_dict() for a in attempts]); return frame
    except Exception as exc: attempts.append(ProviderAttempt("cache","ERROR",str(exc)))
    out=pd.DataFrame(); out.attrs.update(provider=None,provider_attempts=[a.to_dict() for a in attempts]); return out

def provider_runtime_summary(df):
    if df is None or df.empty: return {"provider":None,"failover_used":False,"cached":False,"degraded":True,"quality_status":"UNKNOWN","quality_score":None,"attempts":[]}
    q=df.attrs.get("quality_report") or {}
    return {"provider":df.attrs.get("provider"),"failover_used":bool(df.attrs.get("provider_failover_used")),"cached":bool(df.attrs.get("is_cached")),"cache_age_days":df.attrs.get("cache_age_days"),"degraded":bool(df.attrs.get("degraded_data")),"quality_status":df.attrs.get("data_quality_status",q.get("status","UNKNOWN")),"quality_score":q.get("score"),"last_market_timestamp":df.attrs.get("last_market_timestamp"),"fetched_at_utc":df.attrs.get("fetched_at_utc"),"attempts":df.attrs.get("provider_attempts",[])}

def compare_market_data_providers(ticker,period="1y",interval="1d"):
    symbol=normalize_ticker(ticker); results={}; frames={}
    for name in configured_provider_names():
        fetcher=_PROVIDER_FETCHERS.get(name)
        if not fetcher: results[name]={"status":"SKIP","reason":"unknown provider"}; continue
        try:
            frame=fetcher(symbol,period,interval,attempts=1,backoff_seconds=0) if name=="yfinance" else fetcher(symbol,period,interval)
            q=evaluate_market_frame(frame,name); results[name]={"status":q.status,"quality":q.to_dict(),"last_market_timestamp":frame.attrs.get("last_market_timestamp")}
            if q.status!="FAIL": frames[name]=frame
        except Exception as exc: results[name]={"status":"ERROR","reason":str(exc)}
    pairwise=[]; names=list(frames)
    for i in range(len(names)):
        for j in range(i+1,len(names)):
            a,b=names[i],names[j]; m=frames[a][["Date","Close"]].rename(columns={"Close":"a"}).merge(frames[b][["Date","Close"]].rename(columns={"Close":"b"}),on="Date").dropna()
            if m.empty: pairwise.append({"a":a,"b":b,"overlap_rows":0}); continue
            pct=np.abs(m.a-m.b)/np.maximum(np.abs(m.a),1e-12)*100
            pairwise.append({"a":a,"b":b,"overlap_rows":len(m),"mean_close_diff_pct":float(pct.mean()),"median_close_diff_pct":float(pct.median()),"latest_close_diff_pct":float(pct.iloc[-1])})
    return {"ticker":symbol,"period":period,"interval":interval,"providers":results,"pairwise":pairwise}
