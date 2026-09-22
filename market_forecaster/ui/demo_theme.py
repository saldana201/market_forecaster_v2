"""Modern visual treatment for the anonymous Market Forecaster Demo."""
from __future__ import annotations

import streamlit as st


def inject_demo_theme() -> None:
    st.markdown(
        """
<style>
:root {
    --mf-surface: rgba(15, 23, 42, 0.78);
    --mf-surface-2: rgba(30, 41, 59, 0.72);
    --mf-border: rgba(148, 163, 184, 0.16);
    --mf-text: #f8fafc;
    --mf-muted: #94a3b8;
    --mf-cyan: #22d3ee;
    --mf-blue: #3b82f6;
    --mf-violet: #8b5cf6;
    --mf-green: #22c55e;
}
.block-container {
    max-width: 1440px;
    padding-top: 1.4rem;
    padding-bottom: 3rem;
}
.mf-brandbar {
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:1rem;
    margin:0 0 .85rem 0;
    color:var(--mf-muted);
    font-size:.84rem;
    letter-spacing:.03em;
}
.mf-brand {
    color:var(--mf-text);
    font-weight:700;
}
.mf-live-dot {
    display:inline-block;
    width:8px;
    height:8px;
    margin-right:7px;
    border-radius:999px;
    background:var(--mf-green);
    box-shadow:0 0 14px rgba(34,197,94,.8);
}
.mf-hero {
    position:relative;
    overflow:hidden;
    padding:2rem 2rem 1.8rem 2rem;
    border:1px solid var(--mf-border);
    border-radius:24px;
    background:
        radial-gradient(circle at 88% 8%, rgba(34,211,238,.18), transparent 30%),
        radial-gradient(circle at 72% 86%, rgba(139,92,246,.16), transparent 32%),
        linear-gradient(135deg, rgba(15,23,42,.98), rgba(15,23,42,.82));
    box-shadow:0 24px 70px rgba(2,6,23,.28);
    margin-bottom:1.2rem;
}
.mf-eyebrow {
    display:inline-flex;
    align-items:center;
    gap:.45rem;
    padding:.34rem .7rem;
    border:1px solid rgba(34,211,238,.25);
    border-radius:999px;
    background:rgba(8,145,178,.10);
    color:#a5f3fc;
    font-size:.72rem;
    font-weight:700;
    letter-spacing:.08em;
    text-transform:uppercase;
}
.mf-hero h1 {
    max-width:820px;
    margin:.85rem 0 .55rem 0;
    color:var(--mf-text);
    font-size:clamp(2rem,4vw,3.35rem);
    line-height:1.03;
    letter-spacing:-.04em;
}
.mf-hero p {
    max-width:790px;
    margin:0;
    color:#cbd5e1;
    font-size:1.03rem;
    line-height:1.65;
}
.mf-stat-strip {
    display:grid;
    grid-template-columns:repeat(4,minmax(0,1fr));
    gap:.7rem;
    margin-top:1.35rem;
}
.mf-stat {
    padding:.8rem .9rem;
    border:1px solid rgba(148,163,184,.13);
    border-radius:14px;
    background:rgba(2,6,23,.24);
}
.mf-stat strong {
    display:block;
    color:var(--mf-text);
    font-size:1.02rem;
}
.mf-stat span {
    display:block;
    margin-top:.12rem;
    color:var(--mf-muted);
    font-size:.72rem;
}
.mf-section-kicker {
    color:#67e8f9;
    font-size:.72rem;
    font-weight:700;
    letter-spacing:.08em;
    text-transform:uppercase;
    margin-bottom:.18rem;
}
.mf-market-title {
    margin:0 0 .25rem 0;
    color:var(--mf-text);
    font-size:1.06rem;
    font-weight:750;
}
.mf-market-sub {
    color:var(--mf-muted);
    font-size:.78rem;
    min-height:1.2rem;
}
.mf-status {
    display:inline-block;
    margin-top:.55rem;
    padding:.22rem .5rem;
    border-radius:999px;
    font-size:.66rem;
    font-weight:700;
    letter-spacing:.04em;
}
.mf-status-ready {
    background:rgba(34,197,94,.12);
    color:#86efac;
    border:1px solid rgba(34,197,94,.2);
}
.mf-status-wait {
    background:rgba(245,158,11,.10);
    color:#fcd34d;
    border:1px solid rgba(245,158,11,.18);
}
.mf-card-meta {
    display:grid;
    grid-template-columns:repeat(3,minmax(0,1fr));
    gap:.45rem;
    margin:.8rem 0 .35rem 0;
}
.mf-card-meta div {
    padding:.5rem .55rem;
    border-radius:10px;
    background:rgba(15,23,42,.5);
    border:1px solid rgba(148,163,184,.10);
}
.mf-card-meta span {
    display:block;
    color:var(--mf-muted);
    font-size:.62rem;
}
.mf-card-meta strong {
    display:block;
    margin-top:.1rem;
    color:var(--mf-text);
    font-size:.86rem;
}
.mf-session-note {
    padding:.9rem 1rem;
    border:1px solid rgba(59,130,246,.18);
    border-radius:14px;
    background:rgba(59,130,246,.07);
    color:#bfdbfe;
    font-size:.84rem;
}
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-color:rgba(148,163,184,.14) !important;
    border-radius:18px !important;
    background:linear-gradient(145deg, rgba(15,23,42,.46), rgba(30,41,59,.25));
}
div[data-testid="stButton"] > button {
    min-height:2.65rem;
    border-radius:12px;
    font-weight:650;
    border-color:rgba(148,163,184,.22);
}
div[data-testid="stButton"] > button[kind="primary"] {
    border:none;
    background:linear-gradient(110deg, #0891b2, #2563eb 55%, #7c3aed);
    box-shadow:0 10px 28px rgba(37,99,235,.20);
}
div[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap:.35rem;
    background:rgba(15,23,42,.32);
    border:1px solid rgba(148,163,184,.12);
    border-radius:14px;
    padding:.3rem;
}
div[data-testid="stTabs"] [data-baseweb="tab"] {
    border-radius:10px;
    padding:.45rem .85rem;
}
div[data-testid="stTabs"] [aria-selected="true"] {
    background:rgba(59,130,246,.13);
}
div[data-testid="stMetric"] {
    padding:.72rem .8rem;
    border:1px solid rgba(148,163,184,.11);
    border-radius:12px;
    background:rgba(15,23,42,.28);
}
@media (max-width: 760px) {
    .mf-hero { padding:1.35rem; border-radius:18px; }
    .mf-stat-strip { grid-template-columns:repeat(2,minmax(0,1fr)); }
}
</style>
        """,
        unsafe_allow_html=True,
    )
