"""Reusable HTML/Streamlit building blocks."""

from __future__ import annotations

import html
from typing import Optional

import pandas as pd
import streamlit as st

from components.theme import AQI_COLORS, STATUS
from services.calculations import fmt, is_valid_number
from services.sensors import NORMAL, NOT_CONFIGURED, OFFLINE, WARNING

# --- icons (inline SVG so status never depends on colour alone) -------------
_ICON = {
    "good": '<path d="M5 12.5l4 4 10-10" fill="none" stroke="{c}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "warning": '<path d="M12 3l10 18H2z" fill="{c}"/><path d="M12 10v5M12 18v.5" stroke="#111" stroke-width="2.2" stroke-linecap="round"/>',
    "serious": '<path d="M12 3l10 18H2z" fill="{c}"/><path d="M12 10v5M12 18v.5" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/>',
    "critical": '<path d="M8 2h8l6 6v8l-6 6H8l-6-6V8z" fill="{c}"/><path d="M9 9l6 6M15 9l-6 6" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/>',
    "neutral": '<circle cx="12" cy="12" r="9" fill="none" stroke="{c}" stroke-width="2.2"/><path d="M8 12h8" stroke="{c}" stroke-width="2.2" stroke-linecap="round"/>',
    "info": '<circle cx="12" cy="12" r="10" fill="{c}"/><path d="M12 11v6M12 7.5v.5" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/>',
}

# Logo artwork on a 48×48 grid; reused by the header and as faint watermarks.
LOGO_PATHS = """<path d="M10 14c4-4 8-6 14-6s10 2 14 6" fill="none" stroke="#38c7e8" stroke-width="2.4" stroke-linecap="round"/>
<path d="M15 9c3-2.4 6-3.5 9-3.5s6 1.1 9 3.5" fill="none" stroke="#2a78d6" stroke-width="2" stroke-linecap="round" opacity=".8"/>
<rect x="12" y="15" width="24" height="5" rx="2.5" fill="url(#agsteel)" stroke="#5b6878" stroke-width=".8"/>
<rect x="16" y="20" width="16" height="22" rx="2" fill="url(#agsteel)" stroke="#5b6878" stroke-width=".8"/>
<rect x="21.5" y="23" width="5" height="9" rx="1.2" fill="#0b1f3a"/><rect x="23.5" y="25" width="1" height="5" fill="#38c7e8"/>
<path d="M17 35h14M17 37.5h14M17 40h14" stroke="#5b6878" stroke-width="1"/>
<rect x="13" y="42" width="22" height="3" rx="1.5" fill="#3d4957"/>"""
_LOGO_DEFS = ('<defs><linearGradient id="agsteel" x1="0" x2="1"><stop offset="0" stop-color="#9aa7b6"/>'
              '<stop offset=".5" stop-color="#eef2f6"/><stop offset="1" stop-color="#7d8a99"/></linearGradient></defs>')
LOGO_SVG = f'<svg width="44" height="44" viewBox="0 0 48 48" aria-hidden="true">{_LOGO_DEFS}{LOGO_PATHS}</svg>'


def watermark() -> None:
    """Large, faint AeroGuard mark fixed behind the page content."""
    render_html(f'<div class="ag-watermark"><svg viewBox="0 0 48 48" aria-hidden="true">{_LOGO_DEFS}{LOGO_PATHS}'
                f'</svg><div>AeroGuard</div></div>')

STATE_KIND = {NORMAL: "good", WARNING: "warning", OFFLINE: "critical", NOT_CONFIGURED: "neutral"}
SEVERITY_KIND = {"Info": "info", "Warning": "warning", "Critical": "critical"}


def render_html(markup: str) -> None:
    """Render raw HTML. Lines are joined so Markdown never reads indentation as a code block."""
    st.markdown(" ".join(line.strip() for line in markup.splitlines() if line.strip()), unsafe_allow_html=True)


def icon(kind: str, size: int = 14) -> str:
    color = STATUS.get(kind, "#2a78d6" if kind == "info" else STATUS["neutral"])
    return f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" aria-hidden="true">{_ICON[kind].format(c=color)}</svg>'


def status_html(label: str, kind: str) -> str:
    color = {"good": "var(--ag-good)", "warning": "var(--ag-text)", "serious": "var(--ag-text)",
             "critical": "var(--ag-critical)", "neutral": "var(--ag-muted)", "info": "var(--ag-text)"}[kind]
    return f'<span class="ag-status" style="color:{color}">{icon(kind)}{html.escape(label)}</span>'


def card(body: str, extra_style: str = "") -> None:
    render_html(f'<div class="ag-card" style="{extra_style}">{body}</div>')


def section(title: str, subtitle: str = "", right: str = "") -> None:
    st.markdown(
        f'<div class="ag-section">{html.escape(title)}{right}</div>'
        + (f'<div class="ag-section-sub">{html.escape(subtitle)}</div>' if subtitle else ""),
        unsafe_allow_html=True)


# --- header ---------------------------------------------------------------------

def header(snap) -> None:
    s = snap.settings
    online = not snap.stale
    status = status_html("Online", "good") if online else status_html("Offline / stale", "critical")
    updated = pd.Timestamp(snap.reading.timestamp).strftime("%d %b %Y, %H:%M:%S")
    render_html(f"""
<div class="ag-header">
  <div class="ag-brand">{LOGO_SVG}
    <div><div class="ag-brand-name">Aero<span>Guard</span></div>
    <div class="ag-brand-sub">Intelligent Environmental Monitoring System</div></div>
  </div>
  <div class="ag-chips">
    <span class="ag-chip">Tower <b>{html.escape(s.tower_id)}</b></span>
    <span class="ag-chip">Site <b>{html.escape(s.site_name)}</b></span>
    <span class="ag-chip">{status}</span>
    <span class="ag-chip">Last updated <b>{updated}</b></span>
  </div>
</div>""")


def demo_note(snap) -> None:
    """The single, small demo-mode notice (shown on the Overview page only)."""
    if snap.simulated:
        render_html('<div class="ag-note" style="margin:6px 2px 0">Demo mode · readings are generated by the '
                    'built-in simulator; no tower hardware is connected.</div>')


# --- KPI cards --------------------------------------------------------------------

def pm_status(value, s) -> tuple[str, str]:
    if not is_valid_number(value):
        return "No data", "neutral"
    if value >= s.pm25_critical:
        return "Severe", "critical"
    if value >= s.pm25_high:
        return "High", "serious"
    if value >= s.pm25_low:
        return "Elevated", "warning"
    return "Low", "good"


def pm10_status(value, s) -> tuple[str, str]:
    if not is_valid_number(value):
        return "No data", "neutral"
    if value >= s.pm10_reference * 1.5:
        return "Severe", "critical"
    if value >= s.pm10_reference:
        return "Above reference", "serious"
    if value >= s.pm10_reference * 0.5:
        return "Moderate", "warning"
    return "Low", "good"


def kpi(label: str, value, unit: str, decimals: int, foot: str, simulated: bool,
        sub: str = "", tooltip: str = "", bar_pct: Optional[float] = None) -> None:
    if is_valid_number(value):
        val = f'<div class="ag-kpi-value">{fmt(value, decimals)}<span class="unit">{unit}</span></div>'
    else:
        val = '<div class="ag-kpi-value na">Not available</div>'
    bar = (f'<div class="ag-bar"><div style="width:{max(0, min(100, bar_pct)):.0f}%"></div></div>'
           if bar_pct is not None and is_valid_number(bar_pct) else "")
    t = f' title="{html.escape(tooltip)}"' if tooltip else ""
    card(f'<div{t}><div class="ag-kpi-top"><span class="ag-kpi-label">{html.escape(label)}</span></div>'
         f'{val}{bar}<div class="ag-kpi-foot">{foot}</div>'
         + (f'<div class="ag-kpi-sub">{sub}</div>' if sub else "") + '</div>')


def aqi_card(aqi, simulated: bool) -> None:
    tooltip = ("US EPA AQI computed with the NowCast method from inlet PM2.5 and PM10 only "
               "(2024 PM2.5 breakpoints). Not the official Malaysian API, and other pollutants are not included.")
    if aqi.value is None:
        body = '<div class="ag-kpi-value na">Not available</div>' \
               f'<div class="ag-kpi-foot">{html.escape(aqi.message or "Insufficient data")}</div>'
    else:
        color = AQI_COLORS.get(aqi.category, "#888")
        body = (f'<div class="ag-aqi"><div class="ag-aqi-ring" style="border-color:{color}">{aqi.value}</div>'
                f'<div><div class="ag-aqi-cat">{html.escape(aqi.category)}</div>'
                f'<div class="ag-kpi-sub">Dominant: {aqi.dominant}<br>US EPA method · NowCast · PM only</div></div></div>')
    card(f'<div title="{html.escape(tooltip)}"><div class="ag-kpi-top"><span class="ag-kpi-label">Air Quality (PM AQI)</span>'
         f'</div>{body}</div>')


# --- lists --------------------------------------------------------------------------

def health_list(health, simulated: bool) -> str:
    rows = []
    for h in health:
        kind = STATE_KIND.get(h.state, "neutral")
        rows.append(f'<div class="ag-row"><div>{html.escape(h.name)}<small>{html.escape(h.detail)}</small></div>'
                    f'{status_html(h.state, kind)}</div>')
    return "".join(rows)


def footer(snap) -> None:
    energy = fmt(snap.energy_today.value, 2, "kWh")
    hours = fmt(snap.operating_hours, 0, "h")
    source = f"{snap.adapter.name} — {'stale' if snap.stale else 'live'}"
    render_html(f"""
<div class="ag-footer">
  <div><div class="k">Energy today</div><div class="v">{energy}</div></div>
  <div><div class="k">Operating hours</div><div class="v">{hours}</div></div>
  <div><div class="k">Pollution events (7 d)</div><div class="v">{snap.pollution_episodes_7d}</div></div>
  <div><div class="k">Last update</div><div class="v">{pd.Timestamp(snap.reading.timestamp).strftime('%H:%M:%S')}</div></div>
  <div><div class="k">Data source</div><div class="v">{html.escape(source)}</div></div>
</div>
<div class="ag-note" style="margin-top:8px">Pollution events = periods with inlet PM2.5 at or above the configured
reference ({snap.settings.pm25_reference:.0f} µg/m³) for ≥ 5 min. AeroGuard concept dashboard · prototype software,
not a certified monitoring instrument.</div>""")


def events_table(df: pd.DataFrame, height: int = 260) -> None:
    if df.empty:
        st.info("No events recorded yet.")
        return
    view = pd.DataFrame({
        "Time": pd.to_datetime(df["ts"]).dt.strftime("%d %b %H:%M:%S"),
        "Severity": df["severity"],
        "Source": df["source"],
        "Message": df["message"],
        "Status": df["status"],
    })
    st.dataframe(view, hide_index=True, width="stretch", height=height,
                 column_config={"Message": st.column_config.TextColumn(width="large")})
