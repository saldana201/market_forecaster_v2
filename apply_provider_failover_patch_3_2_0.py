#!/usr/bin/env python3
"""Install Market Forecaster Provider Failover 3.2.0 on working 3.1.0."""
from __future__ import annotations
import re, shutil
from datetime import datetime
from pathlib import Path
PAYLOAD_NAME="mf32_payload_v320"

def find_repo_root(script_dir: Path) -> Path:
    for c in [Path.cwd().resolve(),script_dir.parent.resolve(),script_dir.resolve()]:
        if (c/'market_forecaster'/'app.py').exists(): return c
    raise SystemExit('Could not find market_forecaster_v2 repo root.')

def backup(path: Path, root: Path):
    if path.exists():
        t=path.with_name(path.name+f'.providerbak_{datetime.now().strftime("%Y%m%d_%H%M%S")}'); shutil.copy2(path,t); print(f'backup: {t.relative_to(root)}')

def ensure_after(text,anchor,addition,label):
    if addition.strip() in text: return text
    pos=text.find(anchor)
    if pos<0: raise RuntimeError(f'Could not patch {label}: expected anchor not found')
    pos+=len(anchor); return text[:pos]+addition+text[pos:]

def insert_before_line(text,needle,block,marker,label):
    if marker in text: return text
    lines=text.splitlines(keepends=True)
    for i,line in enumerate(lines):
        if needle in line:
            indent=line[:len(line)-len(line.lstrip())]
            lines.insert(i,''.join(indent+x+'\n' for x in block)); return ''.join(lines)
    raise RuntimeError(f'Could not patch {label}: line containing {needle!r} not found')

script_dir=Path(__file__).resolve().parent; repo_root=find_repo_root(script_dir); payload=script_dir/PAYLOAD_NAME/'market_forecaster'
if not payload.exists(): raise SystemExit(f'3.2 payload missing: {payload}')
config_path=repo_root/'market_forecaster'/'config.py'; config=config_path.read_text(encoding='utf-8')
if '__version__ = "3.2.0"' not in config and '__version__ = "3.1.0"' not in config: raise RuntimeError('3.2 requires working 3.1.0 baseline')

for rel in ['core/data_providers.py','ui/provider_panel.py','api/routes/data_providers.py','tests/test_data_providers.py']:
    src=payload/rel; dst=repo_root/'market_forecaster'/rel
    if not src.exists(): raise RuntimeError(f'Missing patch file: {src}')
    dst.parent.mkdir(parents=True,exist_ok=True)
    if dst.exists(): backup(dst,repo_root)
    shutil.copy2(src,dst); print(f'installed: market_forecaster/{rel}')

# data.py: replace only fetch_stock_data.
data_path=repo_root/'market_forecaster'/'core'/'data.py'; backup(data_path,repo_root); data=data_path.read_text(encoding='utf-8')
if 'fetch_market_data_with_failover' not in data:
    pattern=re.compile(r'def fetch_stock_data\(\n.*?\n\n(?=def data_freshness\()',re.DOTALL)
    replacement='''def fetch_stock_data(\n    ticker: str,\n    period: str = "1y",\n    interval: str = "1d",\n    *,\n    max_attempts: int = 3,\n    backoff_seconds: float = 0.5,\n) -> pd.DataFrame:\n    """Fetch validated market data with provider failover and LKG cache."""\n    from market_forecaster.core.data_providers import fetch_market_data_with_failover\n\n    return fetch_market_data_with_failover(\n        ticker, period, interval,\n        yfinance_attempts=max_attempts,\n        backoff_seconds=backoff_seconds,\n    )\n\n\n'''
    data,count=pattern.subn(replacement,data,count=1)
    if count!=1: raise RuntimeError('Could not patch fetch_stock_data implementation')
data_path.write_text(data,encoding='utf-8'); print('patched: market_forecaster/core/data.py')

# app.py: import panel + visible fallback state + panel render.
app_path=repo_root/'market_forecaster'/'app.py'; backup(app_path,repo_root); app=app_path.read_text(encoding='utf-8')
app=ensure_after(app,'from market_forecaster.ui.operations_panel import render_operations_panel\n','from market_forecaster.ui.provider_panel import render_provider_panel\n','provider UI import')
app=insert_before_line(app,'stock_df = add_technical_indicators(stock_df)',[
    'if stock_df.attrs.get("is_cached"):',
    '    record_operation_event(req.ticker, "data_provider", "WARN", "Last-known-good market-data cache is active", metadata={"provider": stock_df.attrs.get("provider"), "cache_age_days": stock_df.attrs.get("cache_age_days")})',
    '    st.warning(f"Market-data fallback: using {stock_df.attrs.get(\'provider\')} last-known-good cache. Forecasts are running in degraded data mode.")',
    'elif stock_df.attrs.get("provider_failover_used"):',
    '    record_operation_event(req.ticker, "data_provider", "WARN", "Secondary market-data provider is active", metadata={"provider": stock_df.attrs.get("provider")})',
    '    st.info(f"Primary market-data provider unavailable/rejected; using validated fallback provider: {stock_df.attrs.get(\'provider\')}.")',
],'Market-data fallback: using','provider fallback warning')
if 'render_provider_panel(req.ticker' not in app:
    lines=app.splitlines(keepends=True)
    for i,line in enumerate(lines):
        if 'render_operations_panel(req.ticker' in line:
            indent=line[:len(line)-len(line.lstrip())]
            lines.insert(i+1, indent+'st.markdown("---")\n'+indent+'render_provider_panel(req.ticker, st.session_state.get("stock_df"), req.interval)\n')
            app=''.join(lines)
            break
    else:
        raise RuntimeError('Could not patch provider panel: render_operations_panel anchor not found')
app_path.write_text(app,encoding='utf-8'); print('patched: market_forecaster/app.py')

# operations.py: provider fallback should produce WATCH.
ops_path=repo_root/'market_forecaster'/'core'/'operations.py'; backup(ops_path,repo_root); ops=ops_path.read_text(encoding='utf-8')
if '# provider fallback/degraded data' not in ops:
    anchor='''    provider_status = "OK"\n    if freshness.get("status") == "STALE" or len(provider_errors) >= 3:\n        provider_status = "DEGRADED"\n    elif freshness.get("status") in {"WARN", "UNKNOWN"} or provider_errors:\n        provider_status = "WATCH"\n'''
    add=anchor+'''\n    if stock_df is not None and not getattr(stock_df, "empty", True):\n        if stock_df.attrs.get("is_cached") or stock_df.attrs.get("provider_failover_used") or stock_df.attrs.get("degraded_data"):\n            provider_status = "WATCH"  # provider fallback/degraded data\n'''
    if anchor not in ops: raise RuntimeError('Could not patch provider fallback into operations health')
    ops=ops.replace(anchor,add,1)
ops_path.write_text(ops,encoding='utf-8'); print('patched: market_forecaster/core/operations.py')

# API.
api_path=repo_root/'market_forecaster'/'api'/'main.py'; backup(api_path,repo_root); api=api_path.read_text(encoding='utf-8')
api=ensure_after(api,'from market_forecaster.api.routes import operations as operations_routes\n','from market_forecaster.api.routes import data_providers as data_provider_routes\n','provider API import')
api=ensure_after(api,'app.include_router(operations_routes.router, prefix="/api/v1", tags=["Operations"], dependencies=protected)\n','app.include_router(data_provider_routes.router, prefix="/api/v1", tags=["Data Providers"], dependencies=protected)\n','provider API registration')
api_path.write_text(api,encoding='utf-8'); print('patched: market_forecaster/api/main.py')

backup(config_path,repo_root); config=config_path.read_text(encoding='utf-8')
if '__version__ = "3.2.0"' not in config: config=config.replace('__version__ = "3.1.0"','__version__ = "3.2.0"',1)
config_path.write_text(config,encoding='utf-8'); print('patched: market_forecaster/config.py -> 3.2.0')
print('\nProvider Abstraction + Failover 3.2.0 installed successfully.')
print('Next:')
print('  python -m compileall -q market_forecaster')
print('  python -m pytest market_forecaster/tests/test_data_providers.py market_forecaster/tests/test_operations.py -q')
print('  streamlit run market_forecaster/app.py')
