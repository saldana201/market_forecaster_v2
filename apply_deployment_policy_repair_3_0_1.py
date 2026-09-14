#!/usr/bin/env python3
"""Repair Market Forecaster 3.0 deployment-policy install after payload collision.

This installer is intentionally idempotent and never reads a generic repo-root
`payload/` directory. It only consumes `repair_payload_3_0_1` packaged with
this repair release, then repairs the partially modified 2.9/3.0 files in-place.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

PATCH_NAME = "market_forecaster_v2_deployment_policy_repair_3.0.1"


def find_repo_root(script_dir: Path) -> Path:
    candidates = [Path.cwd().resolve(), script_dir.parent.resolve(), script_dir.resolve()]
    for candidate in candidates:
        if (candidate / "market_forecaster" / "app.py").exists():
            return candidate
    raise SystemExit("Could not find market_forecaster_v2 repo root.")


def find_repair_payload(script_dir: Path, repo_root: Path) -> Path:
    candidates = [
        script_dir / "repair_payload_3_0_1" / "market_forecaster",
        script_dir / PATCH_NAME / "repair_payload_3_0_1" / "market_forecaster",
        repo_root / PATCH_NAME / "repair_payload_3_0_1" / "market_forecaster",
    ]
    for candidate in candidates:
        if (candidate / "core" / "deployment_policy.py").exists():
            return candidate
    raise SystemExit(
        "Repair payload not found. Extract the entire 3.0.1 repair ZIP under the repo root."
    )


def backup(path: Path, repo_root: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = path.with_name(path.name + f".repairbak_{stamp}")
    shutil.copy2(path, target)
    print(f"backup: {target.relative_to(repo_root)}")


def ensure_import(text: str, import_line: str, preferred_anchor: str) -> str:
    if import_line in text:
        return text
    if preferred_anchor in text:
        return text.replace(preferred_anchor, preferred_anchor + import_line, 1)
    marker = "\n\ndef "
    if marker in text:
        return text.replace(marker, "\n" + import_line + marker, 1)
    raise RuntimeError(f"Could not insert import: {import_line.strip()}")


script_dir = Path(__file__).resolve().parent
repo_root = find_repo_root(script_dir)
payload_root = find_repair_payload(script_dir, repo_root)

# 1) Restore only the four genuinely new 3.0 files from a uniquely named payload.
for rel in [
    Path("core/deployment_policy.py"),
    Path("ui/deployment_panel.py"),
    Path("api/routes/deployment_policy.py"),
    Path("tests/test_deployment_policy.py"),
]:
    source = payload_root / rel
    dest = repo_root / "market_forecaster" / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    backup(dest, repo_root)
    shutil.copy2(source, dest)
    print(f"installed: market_forecaster/{rel.as_posix()}")

# 2) Repair forecast_audit.py whether it is untouched 2.9 or partially patched 3.0.
audit_path = repo_root / "market_forecaster" / "core" / "forecast_audit.py"
backup(audit_path, repo_root)
audit = audit_path.read_text(encoding="utf-8")

# build_consensus_audit_record signature
build_pos = audit.find("def build_consensus_audit_record(")
if build_pos < 0:
    raise RuntimeError("Could not find build_consensus_audit_record")
build_sig_end = audit.find(") -> dict:", build_pos)
if build_sig_end < 0:
    raise RuntimeError("Could not parse build_consensus_audit_record signature")
build_sig = audit[build_pos:build_sig_end]
if "deployment_decision: Any = None" not in build_sig:
    marker = "    options_promotion: Any = None,\n"
    if marker not in build_sig:
        raise RuntimeError("Could not repair audit build signature")
    build_sig = build_sig.replace(
        marker,
        marker + "    deployment_decision: Any = None,\n",
        1,
    )
    audit = audit[:build_pos] + build_sig + audit[build_sig_end:]

if '"approved_champion"' not in audit:
    anchor = '        "production_candidate": INCUMBENT_CANDIDATE,\n'
    if anchor not in audit:
        raise RuntimeError("Could not repair forecast_audit deployment fields")
    fields = (
        '        "approved_champion": str(getattr(deployment_decision, "approved_champion", INCUMBENT_CANDIDATE)) if deployment_decision is not None else INCUMBENT_CANDIDATE,\n'
        '        "effective_champion": str(getattr(deployment_decision, "effective_champion", INCUMBENT_CANDIDATE)) if deployment_decision is not None else INCUMBENT_CANDIDATE,\n'
        '        "deployment_policy_status": str(getattr(deployment_decision, "policy_status", "DEFAULT_INCUMBENT")) if deployment_decision is not None else "DEFAULT_INCUMBENT",\n'
        '        "deployment_drift_status": str(getattr(deployment_decision, "drift_status", "COLLECTING")) if deployment_decision is not None else "COLLECTING",\n'
        '        "deployment_approval_event_id": getattr(deployment_decision, "approval_event_id", None) if deployment_decision is not None else None,\n'
    )
    audit = audit.replace(anchor, anchor + fields, 1)

# record_consensus_audit signature
record_pos = audit.find("def record_consensus_audit(")
if record_pos < 0:
    raise RuntimeError("Could not find record_consensus_audit")
record_sig_end = audit.find(") -> tuple[str, bool]:", record_pos)
if record_sig_end < 0:
    raise RuntimeError("Could not parse record_consensus_audit signature")
record_sig = audit[record_pos:record_sig_end]
if "deployment_decision: Any = None" not in record_sig:
    marker = "    options_promotion: Any = None,\n"
    if marker not in record_sig:
        raise RuntimeError("Could not repair audit record signature")
    record_sig = record_sig.replace(
        marker,
        marker + "    deployment_decision: Any = None,\n",
        1,
    )
    audit = audit[:record_pos] + record_sig + audit[record_sig_end:]

# Ensure record_consensus_audit forwards deployment_decision.
record_pos = audit.find("def record_consensus_audit(")
build_call = audit.find("build_consensus_audit_record(", record_pos)
if build_call < 0:
    raise RuntimeError("Could not find audit build call")
call_end = audit.find("\n    )", build_call)
if call_end < 0:
    raise RuntimeError("Could not parse audit build call")
segment = audit[build_call:call_end]
if "deployment_decision=deployment_decision" not in segment:
    marker = "        options_promotion=options_promotion,"
    if marker not in segment:
        raise RuntimeError("Could not forward deployment_decision in audit")
    segment = segment.replace(
        marker,
        marker + "\n        deployment_decision=deployment_decision,",
        1,
    )
    audit = audit[:build_call] + segment + audit[call_end:]

audit_path.write_text(audit, encoding="utf-8")
print("repaired: market_forecaster/core/forecast_audit.py")

# 3) Repair consensus_panel.py from pre-2.9, 2.9, or partially patched 3.0.
consensus_path = repo_root / "market_forecaster" / "ui" / "consensus_panel.py"
backup(consensus_path, repo_root)
consensus = consensus_path.read_text(encoding="utf-8")

prod_import = "from market_forecaster.core.production_consensus import build_production_consensus\n"
consensus = ensure_import(
    consensus,
    "from market_forecaster.core.forecast_audit import record_consensus_audit\n",
    prod_import,
)
consensus = ensure_import(
    consensus,
    "from market_forecaster.core.deployment_policy import build_deployment_decision\n",
    "from market_forecaster.core.forecast_audit import record_consensus_audit\n",
)

state_anchor = '    st.session_state["adaptive_production_consensus_result"] = result\n'
if "deployment = build_deployment_decision(ticker, result)" not in consensus:
    if state_anchor not in consensus:
        raise RuntimeError("Could not repair consensus deployment state: session-state anchor missing")
    block = (
        "\n    try:\n"
        "        deployment = build_deployment_decision(ticker, result)\n"
        "        st.session_state[\"deployment_decision\"] = deployment\n"
        "    except Exception as exc:\n"
        "        deployment = None\n"
        "        st.caption(f\"Deployment policy unavailable: {exc}\")\n"
    )
    consensus = consensus.replace(state_anchor, state_anchor + block, 1)

# Restore the 2.9 audit hook if the old generic payload regressed consensus_panel.py.
if "record_consensus_audit(" not in consensus:
    hook_anchor = '        st.caption(f"Deployment policy unavailable: {exc}")\n'
    if hook_anchor not in consensus:
        raise RuntimeError("Could not restore consensus audit hook")
    audit_block = (
        "\n    # Append-only audit: exact Streamlit reruns are fingerprint-deduplicated.\n"
        "    try:\n"
        "        audit_run_id, audit_created = record_consensus_audit(\n"
        "            ticker,\n"
        "            result,\n"
        "            ensemble_result,\n"
        "            stock_df,\n"
        "            options_promotion=promotion,\n"
        "            deployment_decision=deployment,\n"
        "        )\n"
        "        st.session_state[\"forecast_audit_run_id\"] = audit_run_id\n"
        "        st.session_state[\"forecast_audit_created\"] = audit_created\n"
        "    except Exception as exc:\n"
        "        st.caption(f\"Forecast audit unavailable: {exc}\")\n"
    )
    consensus = consensus.replace(hook_anchor, hook_anchor + audit_block, 1)
elif "deployment_decision=deployment" not in consensus:
    call = consensus.find("record_consensus_audit(")
    end = consensus.find("\n        )", call)
    if end < 0:
        raise RuntimeError("Could not parse existing consensus audit call")
    segment = consensus[call:end]
    marker = "            options_promotion=promotion,"
    if marker not in segment:
        raise RuntimeError("Could not extend existing consensus audit call")
    segment = segment.replace(
        marker,
        marker + "\n            deployment_decision=deployment,",
        1,
    )
    consensus = consensus[:call] + segment + consensus[end:]

if "deployed_path = result.consensus" not in consensus:
    fig_anchor = "    fig = go.Figure()\n"
    if fig_anchor not in consensus:
        raise RuntimeError("Could not repair governed chart: figure anchor missing")
    chart_block = (
        "    deployed_path = result.consensus\n"
        "    deployed_lower = result.lower\n"
        "    deployed_upper = result.upper\n"
        "    if deployment is not None:\n"
        "        deployed_path = deployment.path\n"
        "        deployed_lower = deployment.lower\n"
        "        deployed_upper = deployment.upper\n"
        "        if deployment.policy_status == \"FROZEN_FALLBACK\":\n"
        "            st.warning(\n"
        "                f\"Approved challenger {deployment.approved_champion} is frozen by drift policy. \"\n"
        "                f\"Effective deployment has fallen back to {deployment.effective_champion}.\"\n"
        "            )\n"
        "        else:\n"
        "            st.caption(\n"
        "                f\"Deployment policy: approved **{deployment.approved_champion}** · \"\n"
        "                f\"effective **{deployment.effective_champion}** · \"\n"
        "                f\"state **{deployment.policy_status}**\"\n"
        "            )\n\n"
    )
    consensus = consensus.replace(fig_anchor, chart_block + fig_anchor, 1)

consensus = consensus.replace("x=result.dates, y=result.upper,", "x=result.dates, y=deployed_upper,", 1)
consensus = consensus.replace("x=result.dates, y=result.lower,", "x=result.dates, y=deployed_lower,", 1)

if 'name="Deployed Champion"' not in consensus:
    insert_marker = "    if result.xgb_anchors:\n"
    if insert_marker not in consensus:
        raise RuntimeError("Could not repair governed chart: XGB anchor section missing")
    governed_trace = (
        "    if deployment is not None and deployment.effective_champion != \"adaptive_production_consensus\":\n"
        "        fig.add_trace(go.Scatter(\n"
        "            x=result.dates,\n"
        "            y=deployed_path,\n"
        "            mode=\"lines\",\n"
        "            name=\"Deployed Champion\",\n"
        "            line=dict(width=4, dash=\"solid\", color=\"#0f766e\"),\n"
        "        ))\n\n"
    )
    consensus = consensus.replace(insert_marker, governed_trace + insert_marker, 1)

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
print("repaired: market_forecaster/ui/consensus_panel.py")

# 4) App integration.
app_path = repo_root / "market_forecaster" / "app.py"
backup(app_path, repo_root)
app = app_path.read_text(encoding="utf-8")
if "from market_forecaster.ui.deployment_panel import render_deployment_policy_panel" not in app:
    anchor = "from market_forecaster.ui.governance_panel import render_governance_panel\n"
    if anchor not in app:
        raise RuntimeError("Could not repair app deployment import")
    app = app.replace(anchor, anchor + "from market_forecaster.ui.deployment_panel import render_deployment_policy_panel\n", 1)
if "render_deployment_policy_panel(req.ticker)" not in app:
    anchor = '        render_governance_panel(req.ticker, st.session_state.get("stock_df"))\n        st.markdown("---")\n'
    if anchor not in app:
        raise RuntimeError("Could not repair Backtest deployment panel")
    app = app.replace(
        anchor,
        '        render_governance_panel(req.ticker, st.session_state.get("stock_df"))\n'
        '        st.markdown("---")\n'
        '        render_deployment_policy_panel(req.ticker)\n'
        '        st.markdown("---")\n',
        1,
    )
app_path.write_text(app, encoding="utf-8")
print("repaired: market_forecaster/app.py")

# 5) API integration.
api_path = repo_root / "market_forecaster" / "api" / "main.py"
backup(api_path, repo_root)
api = api_path.read_text(encoding="utf-8")
if "deployment_policy as deployment_policy_routes" not in api:
    anchor = "from market_forecaster.api.routes import audit as audit_routes\n"
    if anchor not in api:
        raise RuntimeError("Could not repair deployment API import")
    api = api.replace(anchor, anchor + "from market_forecaster.api.routes import deployment_policy as deployment_policy_routes\n", 1)
if "deployment_policy_routes.router" not in api:
    anchor = 'app.include_router(audit_routes.router, prefix="/api/v1", tags=["Forecast Audit"], dependencies=protected)\n'
    if anchor not in api:
        raise RuntimeError("Could not repair deployment API registration")
    api = api.replace(
        anchor,
        anchor + 'app.include_router(deployment_policy_routes.router, prefix="/api/v1", tags=["Deployment Policy"], dependencies=protected)\n',
        1,
    )
api_path.write_text(api, encoding="utf-8")
print("repaired: market_forecaster/api/main.py")

# 6) Version bump.
config_path = repo_root / "market_forecaster" / "config.py"
backup(config_path, repo_root)
config = config_path.read_text(encoding="utf-8")
if '__version__ = "3.0.1"' not in config:
    if '__version__ = "3.0.0"' in config:
        config = config.replace('__version__ = "3.0.0"', '__version__ = "3.0.1"', 1)
    elif '__version__ = "2.9.0"' in config:
        config = config.replace('__version__ = "2.9.0"', '__version__ = "3.0.1"', 1)
    else:
        raise RuntimeError("Expected app version 2.9.0 or 3.0.0")
config_path.write_text(config, encoding="utf-8")
print("repaired: market_forecaster/config.py -> 3.0.1")

print("\n3.0.1 repair installed successfully.")
print("Run:")
print("  python -m compileall -q market_forecaster")
print("  python -m pytest market_forecaster/tests/test_forecast_audit.py market_forecaster/tests/test_deployment_policy.py -q")
print("  streamlit run market_forecaster/app.py")
