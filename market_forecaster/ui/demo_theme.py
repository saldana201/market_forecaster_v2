"""Premium visual treatment for the anonymous Market Forecaster Demo."""
from __future__ import annotations

import streamlit as st


def inject_demo_theme() -> None:
    st.markdown(
        """
<style>
:root {
    --mf-bg: #07111f;
    --mf-panel: rgba(12, 24, 42, .82);
    --mf-panel-2: rgba(18, 33, 55, .78);
    --mf-border: rgba(148, 163, 184, .16);
    --mf-border-strong: rgba(96, 165, 250, .30);
    --mf-text: #f8fafc;
    --mf-muted: #91a4bd;
    --mf-cyan: #22d3ee;
    --mf-blue: #3b82f6;
    --mf-violet: #8b5cf6;
    --mf-green: #22c55e;
    --mf-red: #fb7185;
    --mf-amber: #f59e0b;
}

.block-container {
    max-width: 1500px;
    padding-top: 1rem;
    padding-bottom: 3.25rem;
}

.mf-brandbar {
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:1rem;
    margin:0 0 .9rem 0;
    padding:.15rem .2rem;
    color:var(--mf-muted);
    font-size:.8rem;
    letter-spacing:.04em;
}
.mf-brand {
    color:var(--mf-text);
    font-weight:800;
}
.mf-live-dot {
    display:inline-block;
    width:8px;
    height:8px;
    margin-right:7px;
    border-radius:999px;
    background:var(--mf-green);
    box-shadow:0 0 18px rgba(34,197,94,.9);
}

.mf-hero {
    position:relative;
    overflow:hidden;
    padding:2.3rem 2.35rem 2rem 2.35rem;
    border:1px solid rgba(96,165,250,.20);
    border-radius:28px;
    background:
        radial-gradient(circle at 92% 0%, rgba(34,211,238,.22), transparent 28%),
        radial-gradient(circle at 77% 92%, rgba(124,58,237,.22), transparent 34%),
        linear-gradient(135deg, rgba(8,18,34,.99), rgba(13,29,51,.95) 58%, rgba(18,20,46,.92));
    box-shadow:0 28px 90px rgba(2,6,23,.38), inset 0 1px 0 rgba(255,255,255,.03);
    margin-bottom:1.35rem;
}
.mf-hero::after {
    content:"";
    position:absolute;
    width:280px;
    height:280px;
    right:-85px;
    top:-95px;
    border-radius:50%;
    border:1px solid rgba(103,232,249,.13);
    box-shadow:0 0 0 42px rgba(103,232,249,.025), 0 0 0 88px rgba(139,92,246,.02);
    pointer-events:none;
}
.mf-eyebrow {
    display:inline-flex;
    align-items:center;
    gap:.45rem;
    padding:.36rem .74rem;
    border:1px solid rgba(34,211,238,.24);
    border-radius:999px;
    background:rgba(8,145,178,.10);
    color:#a5f3fc;
    font-size:.7rem;
    font-weight:800;
    letter-spacing:.09em;
    text-transform:uppercase;
}
.mf-hero h1 {
    max-width:900px;
    margin:.9rem 0 .62rem 0;
    color:var(--mf-text);
    font-size:clamp(2.2rem,4.2vw,3.85rem);
    line-height:1.0;
    letter-spacing:-.045em;
}
.mf-hero p {
    max-width:830px;
    margin:0;
    color:#cbd5e1;
    font-size:1.02rem;
    line-height:1.68;
}
.mf-stat-strip {
    display:grid;
    grid-template-columns:repeat(4,minmax(0,1fr));
    gap:.72rem;
    margin-top:1.55rem;
}
.mf-stat {
    padding:.9rem 1rem;
    border:1px solid rgba(148,163,184,.12);
    border-radius:15px;
    background:rgba(2,6,23,.28);
    backdrop-filter: blur(8px);
}
.mf-stat strong {
    display:block;
    color:var(--mf-text);
    font-size:1.02rem;
    font-weight:800;
}
.mf-stat span {
    display:block;
    margin-top:.13rem;
    color:var(--mf-muted);
    font-size:.7rem;
}

.mf-section-head {
    display:flex;
    justify-content:space-between;
    align-items:end;
    gap:1rem;
    margin:1.1rem 0 .55rem 0;
}
.mf-section-title {
    color:var(--mf-text);
    font-size:1.35rem;
    font-weight:800;
    letter-spacing:-.02em;
}
.mf-section-copy {
    color:var(--mf-muted);
    font-size:.8rem;
}

.mf-market-card {
    position:relative;
    overflow:hidden;
    padding:1.05rem 1.05rem .95rem 1.05rem;
    border:1px solid var(--mf-border);
    border-radius:20px;
    background:
        linear-gradient(150deg, rgba(21,39,64,.78), rgba(8,19,34,.84));
    box-shadow:0 14px 36px rgba(2,6,23,.19);
    min-height:220px;
}
.mf-market-card:hover {
    border-color:rgba(96,165,250,.34);
    box-shadow:0 18px 48px rgba(2,6,23,.28);
}
.mf-market-card-selected {
    border-color:rgba(34,211,238,.48);
    box-shadow:0 0 0 1px rgba(34,211,238,.12), 0 18px 50px rgba(8,145,178,.16);
    background:
        radial-gradient(circle at 100% 0%, rgba(34,211,238,.11), transparent 32%),
        linear-gradient(150deg, rgba(20,45,72,.92), rgba(7,20,36,.90));
}
.mf-card-top {
    display:flex;
    justify-content:space-between;
    align-items:flex-start;
    gap:.6rem;
}
.mf-symbol-lockup {
    display:flex;
    align-items:center;
    gap:.68rem;
}
.mf-symbol-icon {
    display:flex;
    align-items:center;
    justify-content:center;
    width:40px;
    height:40px;
    border-radius:13px;
    color:#e0f2fe;
    font-size:.92rem;
    font-weight:900;
    background:linear-gradient(145deg, rgba(14,165,233,.20), rgba(124,58,237,.18));
    border:1px solid rgba(125,211,252,.18);
}
.mf-ticker {
    color:var(--mf-text);
    font-size:1.24rem;
    font-weight:850;
    letter-spacing:-.02em;
    line-height:1.05;
}
.mf-company {
    color:var(--mf-muted);
    font-size:.73rem;
    margin-top:.16rem;
}
.mf-sector-chip {
    display:inline-flex;
    padding:.25rem .48rem;
    border-radius:999px;
    font-size:.61rem;
    color:#b9d7f5;
    border:1px solid rgba(148,163,184,.14);
    background:rgba(15,23,42,.44);
    white-space:nowrap;
}
.mf-price-row {
    display:flex;
    justify-content:space-between;
    align-items:flex-end;
    gap:.8rem;
    margin-top:1.05rem;
}
.mf-price {
    color:var(--mf-text);
    font-size:1.5rem;
    font-weight:850;
    letter-spacing:-.03em;
}
.mf-price-label {
    color:var(--mf-muted);
    font-size:.62rem;
    margin-bottom:.14rem;
}
.mf-move {
    display:inline-flex;
    align-items:center;
    padding:.3rem .55rem;
    border-radius:999px;
    font-size:.72rem;
    font-weight:800;
}
.mf-move-up {
    color:#86efac;
    background:rgba(34,197,94,.11);
    border:1px solid rgba(34,197,94,.18);
}
.mf-move-down {
    color:#fda4af;
    background:rgba(244,63,94,.10);
    border:1px solid rgba(244,63,94,.18);
}
.mf-move-flat {
    color:#cbd5e1;
    background:rgba(148,163,184,.09);
    border:1px solid rgba(148,163,184,.14);
}
.mf-prob-wrap {
    margin-top:.95rem;
}
.mf-prob-head {
    display:flex;
    justify-content:space-between;
    color:var(--mf-muted);
    font-size:.64rem;
    margin-bottom:.35rem;
}
.mf-prob-head strong {
    color:#dbeafe;
    font-weight:800;
}
.mf-prob-track {
    height:7px;
    overflow:hidden;
    border-radius:999px;
    background:rgba(148,163,184,.12);
}
.mf-prob-fill {
    height:100%;
    border-radius:999px;
    background:linear-gradient(90deg, #0891b2, #2563eb 55%, #7c3aed);
}
.mf-card-footer {
    display:flex;
    justify-content:space-between;
    gap:.55rem;
    align-items:center;
    margin-top:.9rem;
    color:var(--mf-muted);
    font-size:.62rem;
}
.mf-ready {
    color:#86efac;
}
.mf-wait {
    color:#fcd34d;
}
.mf-selected-tag {
    color:#67e8f9;
    font-weight:800;
}

.mf-session-note {
    margin-top:.8rem;
    padding:1rem 1.1rem;
    border:1px solid rgba(59,130,246,.20);
    border-radius:16px;
    background:linear-gradient(120deg, rgba(37,99,235,.08), rgba(124,58,237,.06));
    color:#c7d7ff;
    font-size:.82rem;
}
.mf-session-note strong {
    color:#f8fafc;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    border-color:rgba(148,163,184,.13) !important;
    border-radius:20px !important;
    background:linear-gradient(145deg, rgba(12,24,42,.66), rgba(21,35,56,.42));
    box-shadow:0 10px 32px rgba(2,6,23,.12);
}

div[data-testid="stButton"] > button {
    min-height:2.6rem;
    border-radius:12px;
    font-weight:700;
    border-color:rgba(148,163,184,.20);
}
div[data-testid="stButton"] > button[kind="primary"] {
    border:none;
    background:linear-gradient(110deg, #0891b2, #2563eb 52%, #7c3aed);
    box-shadow:0 10px 26px rgba(37,99,235,.22);
}

div[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap:.38rem;
    background:rgba(8,18,34,.60);
    border:1px solid rgba(148,163,184,.12);
    border-radius:15px;
    padding:.32rem;
}
div[data-testid="stTabs"] [data-baseweb="tab"] {
    border-radius:11px;
    padding:.5rem .95rem;
    font-weight:650;
    color:#cbd5e1 !important;
    opacity:1 !important;
    transition:background .16s ease, color .16s ease, border-color .16s ease;
}
div[data-testid="stTabs"] [data-baseweb="tab"] p,
div[data-testid="stTabs"] [data-baseweb="tab"] span {
    color:inherit !important;
    opacity:1 !important;
}
div[data-testid="stTabs"] [data-baseweb="tab"]:hover {
    color:#ffffff !important;
    background:rgba(59,130,246,.10);
}
div[data-testid="stTabs"] [aria-selected="true"] {
    color:#f8fafc !important;
    background:linear-gradient(110deg, rgba(8,145,178,.22), rgba(37,99,235,.24));
    box-shadow:inset 0 0 0 1px rgba(96,165,250,.18);
}
div[data-testid="stTabs"] [aria-selected="true"] p,
div[data-testid="stTabs"] [aria-selected="true"] span {
    color:#f8fafc !important;
}

div[data-testid="stMetric"] {
    padding:.8rem .9rem;
    border:1px solid rgba(148,163,184,.11);
    border-radius:14px;
    background:rgba(8,18,34,.38);
}

div[data-testid="stTextInput"] input,
div[data-testid="stNumberInput"] input {
    border-radius:12px !important;
}

@media (max-width: 980px) {
    .mf-stat-strip { grid-template-columns:repeat(2,minmax(0,1fr)); }
}
@media (max-width: 760px) {
    .mf-hero { padding:1.45rem; border-radius:20px; }
    .mf-stat-strip { grid-template-columns:repeat(2,minmax(0,1fr)); }
    .mf-market-card { min-height:0; }
    .mf-section-head { align-items:flex-start; flex-direction:column; gap:.25rem; }
}
</style>
        """,
        unsafe_allow_html=True,
    )
