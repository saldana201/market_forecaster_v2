"""Shared Market Forecaster visual components."""
from __future__ import annotations

import html
from collections.abc import Iterable

import streamlit as st


def render_page_header(
    title: str,
    subtitle: str,
    *,
    eyebrow: str | None = None,
    badge: str | None = None,
) -> None:
    eyebrow_html = (
        f'<span class="mf-eyebrow">{html.escape(eyebrow)}</span>'
        if eyebrow
        else ""
    )
    badge_html = (
        f'<span class="mf-page-badge">{html.escape(badge)}</span>'
        if badge
        else ""
    )
    st.markdown(
        f"""
<div class="mf-page-head">
  <div class="mf-page-head-copy">
    {eyebrow_html}
    <div class="mf-page-title-row">
      <h1>{html.escape(title)}</h1>
      {badge_html}
    </div>
    <p>{html.escape(subtitle)}</p>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_strip(items: Iterable[dict]) -> None:
    cards: list[str] = []
    for item in items:
        label = html.escape(str(item.get("label") or ""))
        value = html.escape(str(item.get("value") or "—"))
        caption = html.escape(str(item.get("caption") or ""))
        tone = str(item.get("tone") or "neutral").lower()
        if tone not in {"neutral", "positive", "negative", "accent", "warning"}:
            tone = "neutral"
        cards.append(
            f"""
<div class="mf-kpi mf-kpi-{tone}">
  <div class="mf-kpi-label">{label}</div>
  <div class="mf-kpi-value">{value}</div>
  <div class="mf-kpi-caption">{caption}</div>
</div>
            """
        )
    st.markdown(
        '<div class="mf-kpi-grid">' + "".join(cards) + "</div>",
        unsafe_allow_html=True,
    )


def render_section_header(
    title: str,
    subtitle: str | None = None,
    *,
    badge: str | None = None,
) -> None:
    badge_html = (
        f'<span class="mf-section-badge">{html.escape(badge)}</span>'
        if badge
        else ""
    )
    copy_html = (
        f'<div class="mf-section-copy">{html.escape(subtitle)}</div>'
        if subtitle
        else ""
    )
    st.markdown(
        f"""
<div class="mf-section-head">
  <div>
    <div class="mf-section-title">{html.escape(title)} {badge_html}</div>
    {copy_html}
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )
