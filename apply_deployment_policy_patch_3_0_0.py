#!/usr/bin/env python3
"""Install Market Forecaster Drift + Deployment Policy 3.0.0."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def find_repo_root(package_dir: Path) -> Path:
    candidates = [Path.cwd().resolve(), package_dir.parent.resolve(), package_dir.resolve()]
    for candidate in candidates:
        if (candidate / "market_forecaster" / "app.py").exists():
            return candidate
    raise SystemExit(
        "Could not find market_forecaster_v2 repo root. "
        "Run from repo root or extract this patch folder directly under it."
    )


def backup(path: Path, repo_root: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = path.with_name(path.name + f".bak_{stamp}")
    shutil.copy2(path, target)
    print(f"backup: {target.relative_to(repo_root)}")


def replace_once(text: str, needle: str, replacement: str, label: str) -> str:
    if replacement in text:
        return text
    if needle not in text:
        raise RuntimeError(f"Could not patch {label}: expected anchor not found")
    return text.replace(needle, replacement, 1)


package_dir = Path(__file__).resolve().parent
repo_root = find_repo_root(package_dir)
payload_root = package_dir / "payload" / "market_forecaster"
if not payload_root.exists():
    raise SystemExit(f"Payload not found: {payload_root}")

for source in payload_root.rglob("*"):
    if source.is_dir():
        continue
    rel = source.relative_to(payload_root)
    dest = repo_root / "market_forecaster" / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        backup(dest, repo_root)
    shutil.copy2(source, dest)
    print(f"installed: market_forecaster/{rel.as_posix()}")

# Extend audit records with approved/effective champion state.
audit_path = repo_root / "market_forecaster" / "core" / "forecast_audit.py"
backup(audit_path, repo_root)
audit = audit_path.read_text(encoding="utf-8")

audit = replace_once(
    audit,
    "    options_promotion: Any = None,\n    horizons: Iterable[int] = AUDIT_HORIZONS,\n",
    "    options_promotion: Any = None,\n"
    "    deployment_decision: Any = None,\n"
    "    horizons: Iterable[int] = AUDIT_HORIZONS,\n",
    "audit build signature",
)
audit = replace_once(
    audit,
    '        "production_candidate": INCUMBENT_CANDIDATE,\n',
    '        "production_candidate": INCUMBENT_CANDIDATE,\n'
    '        "approved_champion": str(getattr(deployment_decision, "approved_champion", INCUMBENT_CANDIDATE)) if deployment_decision is not None else INCUMBENT_CANDIDATE,\n'
    '        "effective_champion": str(getattr(deployment_decision, "effective_champion", INCUMBENT_CANDIDATE)) if deployment_decision is not None else INCUMBENT_CANDIDATE,\n'
    '        "deployment_policy_status": str(getattr(deployment_decision, "policy_status", "DEFAULT_INCUMBENT")) if deployment_decision is not None else "DEFAULT_INCUMBENT",\n'
    '        "deployment_drift_status": str(getattr(deployment_decision, "drift_status", "COLLECTING")) if deployment_decision is not None else "COLLECTING",\n'
    '        "deployment_approval_event_id": getattr(deployment_decision, "approval_event_id", None) if deployment_decision is not None else None,\n',
    "audit deployment fields",
)
audit = replace_once(
    audit,
    "    options_promotion: Any = None,\n    app_version: str | None = None,\n",
    "    options_promotion: Any = None,\n"
    "    deployment_decision: Any = None,\n"
    "    app_version: str | None = None,\n",
    "audit record signature",
)
audit = replace_once(
    audit,
    "        options_promotion=options_promotion,\n    )\n",
    "        options_promotion=options_promotion,\n"
    "        deployment_decision=deployment_decision,\n"
    "    )\n",
    "audit build call",
)
audit_path.write_text(audit, encoding="utf-8")
print("patched: market_forecaster/core/forecast_audit.py")

# Make the consensus panel resolve the explicit deployment champion.
consensus_path = repo_root / "market_forecaster" / "ui" / "consensus_panel.py"
backup(consensus_path, repo_root)
consensus = consensus_path.read_text(encoding="utf-8")
consensus = replace_once(
    consensus,
    "from market_forecaster.core.forecast_audit import record_consensus_audit\n",
    "from market_forecaster.core.forecast_audit import record_consensus_audit\n"
    "from market_forecaster.core.deployment_policy import build_deployment_decision\n",
    "consensus deployment import",
)
state_anchor = '    st.session_state["adaptive_production_consensus_result"] = result\n'
state_replacement = '''    st.session_state["adaptive_production_consensus_result"] = result

    try:
        deployment = build_deployment_decision(ticker, result)
        st.session_state["deployment_decision"] = deployment
    except Exception as exc:
        deployment = None
        st.caption(f"Deployment policy unavailable: {exc}")
'''
consensus = replace_once(consensus, state_anchor, state_replacement, "consensus deployment state")
consensus = replace_once(
    consensus,
    "            options_promotion=promotion,\n        )\n",
    "            options_promotion=promotion,\n"
    "            deployment_decision=deployment,\n"
    "        )\n",
    "consensus audit deployment",
)
figure_anchor = "    fig = go.Figure()\n"
figure_replacement = '''    deployed_path = result.consensus
    deployed_lower = result.lower
    deployed_upper = result.upper
    deployed_name = "Adaptive Production Consensus"
    if deployment is not None:
        deployed_path = deployment.path
        deployed_lower = deployment.lower
        deployed_upper = deployment.upper
        deployed_name = f"Deployed Champion: {deployment.effective_champion}"
        if deployment.policy_status == "FROZEN_FALLBACK":
            st.warning(
                f"Approved challenger {deployment.approved_champion} is frozen by drift policy. "
                f"Effective deployment has fallen back to {deployment.effective_champion}."
            )
        else:
            st.caption(
                f"Deployment policy: approved **{deployment.approved_champion}** · "
                f"effective **{deployment.effective_champion}** · "
                f"state **{deployment.policy_status}**"
            )

    fig = go.Figure()
'''
consensus = replace_once(consensus, figure_anchor, figure_replacement, "consensus deployed path")
consensus = consensus.replace("x=result.dates, y=result.upper,", "x=result.dates, y=deployed_upper,", 1)
consensus = consensus.replace("x=result.dates, y=result.lower,", "x=result.dates, y=deployed_lower,", 1)

adaptive_trace = '''    fig.add_trace(go.Scatter(
        x=result.dates, y=result.consensus,
        mode="lines",
        name="Adaptive Production Consensus" if opt_count else "Production Consensus",
        line=dict(width=3, color="#047857"),
    ))
'''
deployed_trace = '''    if deployment is not None and deployment.effective_champion != "adaptive_production_consensus":
        fig.add_trace(go.Scatter(
            x=result.dates, y=result.consensus,
            mode="lines",
            name="Adaptive Candidate",
            line=dict(width=2, dash="dash", color="#059669"),
        ))

    fig.add_trace(go.Scatter(
        x=result.dates, y=deployed_path,
        mode="lines",
        name=deployed_name,
        line=dict(width=3, color="#047857"),
    ))
'''
consensus = replace_once(consensus, adaptive_trace, deployed_trace, "deployed champion trace")
consensus = consensus.replace(
    'title=f"{ticker} — Adaptive Production Consensus",',
    'title=f"{ticker} — Governed Production Forecast",',
    1,
)
consensus = consensus.replace(
    '(result.consensus[-1] / result.consensus[0] - 1.0) * 100\n            if result.consensus[0] else 0.0',
    '(deployed_path[-1] / deployed_path[0] - 1.0) * 100\n            if deployed_path[0] else 0.0',
    1,
)
consensus_path.write_text(consensus, encoding="utf-8")
print("patched: market_forecaster/ui/consensus_panel.py")

# Add deployment policy UI to Backtest.
app_path = repo_root / "market_forecaster" / "app.py"
backup(app_path, repo_root)
app = app_path.read_text(encoding="utf-8")
app = replace_once(
    app,
    "from market_forecaster.ui.governance_panel import render_governance_panel\n",
    "from market_forecaster.ui.governance_panel import render_governance_panel\n"
    "from market_forecaster.ui.deployment_panel import render_deployment_policy_panel\n",
    "app deployment import",
)
app = replace_once(
    app,
    '        render_governance_panel(req.ticker, st.session_state.get("stock_df"))\n        st.markdown("---")\n',
    '        render_governance_panel(req.ticker, st.session_state.get("stock_df"))\n'
    '        st.markdown("---")\n'
    '        render_deployment_policy_panel(req.ticker)\n'
    '        st.markdown("---")\n',
    "Backtest deployment panel",
)
app_path.write_text(app, encoding="utf-8")
print("patched: market_forecaster/app.py")

# Register policy API.
api_path = repo_root / "market_forecaster" / "api" / "main.py"
backup(api_path, repo_root)
api = api_path.read_text(encoding="utf-8")
api = replace_once(
    api,
    "from market_forecaster.api.routes import audit as audit_routes\n",
    "from market_forecaster.api.routes import audit as audit_routes\n"
    "from market_forecaster.api.routes import deployment_policy as deployment_policy_routes\n",
    "API deployment import",
)
api = replace_once(
    api,
    'app.include_router(audit_routes.router, prefix="/api/v1", tags=["Forecast Audit"], dependencies=protected)\n',
    'app.include_router(audit_routes.router, prefix="/api/v1", tags=["Forecast Audit"], dependencies=protected)\n'
    'app.include_router(deployment_policy_routes.router, prefix="/api/v1", tags=["Deployment Policy"], dependencies=protected)\n',
    "API deployment registration",
)
api_path.write_text(api, encoding="utf-8")
print("patched: market_forecaster/api/main.py")

# Version bump.
config_path = repo_root / "market_forecaster" / "config.py"
backup(config_path, repo_root)
config = config_path.read_text(encoding="utf-8")
if '__version__ = "3.0.0"' not in config:
    if '__version__ = "2.9.0"' not in config:
        raise RuntimeError("Expected Market Forecaster 2.9.0 baseline in config.py")
    config = config.replace('__version__ = "2.9.0"', '__version__ = "3.0.0"', 1)
config_path.write_text(config, encoding="utf-8")
print("patched: market_forecaster/config.py -> 3.0.0")

print("\nDrift Monitoring + Deployment Policy 3.0.0 installed successfully.")
print("Next:")
print("  python -m compileall -q market_forecaster")
print("  pytest market_forecaster/tests/test_deployment_policy.py -q")
print("  streamlit run market_forecaster/app.py")
