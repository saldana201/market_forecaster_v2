from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path


def find_package_dir() -> Path:
    cwd = Path.cwd()
    candidates = [cwd / "market_forecaster", cwd]
    for candidate in candidates:
        if (candidate / "ui" / "components.py").exists() and (candidate / "core" / "signals.py").exists():
            return candidate
    raise SystemExit(
        "Could not find market_forecaster/ui/components.py and market_forecaster/core/signals.py. "
        "Run this script from the repository root or from the market_forecaster folder."
    )


def backup(path: Path) -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = path.with_suffix(path.suffix + f".bak_{stamp}")
    shutil.copy2(path, dest)
    print(f"Backup: {dest}")


def patch_components(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"def component_breakdown\(components: dict\):.*?(?=\n\n# -------------------------------------------------------------------\n# Metric row)",
        re.S,
    )
    replacement = '''def component_breakdown(components: dict):
    """Show a horizontal breakdown of numeric signal component scores.

    Signal metadata may occasionally contain descriptive strings. Production UI
    must never crash because of a non-numeric diagnostic value, so only finite
    numeric values are charted here.
    """
    import math
    import plotly.graph_objects as go

    if not components:
        return

    numeric_items = []
    for key, value in components.items():
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric):
            numeric_items.append((str(key), numeric))

    if not numeric_items:
        st.caption("No numeric signal-component scores are available for this run.")
        return

    labels = [key for key, _ in numeric_items]
    values = [value for _, value in numeric_items]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=values,
        y=labels,
        orientation="h",
        marker_color=[
            "#22c55e" if value > 0 else "#ef4444" if value < 0 else "#9ca3af"
            for value in values
        ],
        text=[f"{value:+.2f}" for value in values],
        textposition="outside",
    ))
    max_abs = max(1.0, max(abs(value) for value in values))
    axis_limit = min(2.5, max_abs * 1.2)
    fig.update_layout(
        height=max(200, len(values) * 40),
        margin=dict(l=10, r=40, t=10, b=10),
        xaxis=dict(range=[-axis_limit, axis_limit], title="Score"),
        yaxis=dict(autorange="reversed"),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)
'''
    new_text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise SystemExit(f"Could not locate component_breakdown() in {path}")
    backup(path)
    path.write_text(new_text, encoding="utf-8")
    print(f"Patched: {path}")


def patch_signals(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    replacements = {
        'components["rsi"] = "oversold"': 'components["rsi"] = 1.0',
        'components["rsi"] = "overbought"': 'components["rsi"] = -1.0',
        'components["rsi"] = f"{rsi:.0f}"': 'components["rsi"] = 0.0',
        'components["macd"] = "bullish" if macd_hist > 0 else "bearish"': 'components["macd"] = 0.5 if macd_hist > 0 else -0.5',
        'components["trend"] = "above SMA20" if trend_up > 0 else "below SMA20"': 'components["trend"] = trend_up * 0.5',
    }

    changed = 0
    for old, new in replacements.items():
        if old in text:
            text = text.replace(old, new)
            changed += 1
        elif new in text:
            # Already patched; keep idempotent.
            changed += 1
        else:
            raise SystemExit(f"Expected signal snippet not found in {path}: {old}")

    if changed != len(replacements):
        raise SystemExit(f"Signal patch incomplete for {path}")

    backup(path)
    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")


def main() -> None:
    package_dir = find_package_dir()
    print(f"Market Forecaster package: {package_dir}")
    patch_components(package_dir / "ui" / "components.py")
    patch_signals(package_dir / "core" / "signals.py")
    print("\nHotfix 2.1.1 applied successfully.")
    print("Restart Streamlit with: streamlit run app.py   (when inside market_forecaster)")


if __name__ == "__main__":
    main()
