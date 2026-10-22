"""B. Live Air Quality — detailed sensor readings."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components import charts, ui
from views.common import range_picker, snap


def render() -> None:
    sn = snap()
    r, s, sim = sn.reading, sn.settings, sn.simulated
    live = None if sn.stale else r
    st.subheader("Live air quality")

    cols = st.columns(4)
    lab25, k25 = ui.pm_status(live and live.inlet_pm25, s)
    lab10, k10 = ui.pm10_status(live and live.inlet_pm10, s)
    items = [
        ("PM2.5", live and live.inlet_pm25, "µg/m³", 1, ui.status_html(lab25, k25)),
        ("PM10", live and live.inlet_pm10, "µg/m³", 0, ui.status_html(lab10, k10)),
        ("Temperature", live and live.temperature_c, "°C", 1, "<span class='ag-note'>Ambient, at inlet</span>"),
        ("Relative humidity", live and live.humidity_pct, "%", 0, "<span class='ag-note'>Ambient, at inlet</span>"),
    ]
    for col, (label, val, unit, dec, foot) in zip(cols, items):
        with col:
            ui.kpi(label, val, unit, dec, foot, sim)
    configured = sn.adapter.channels()
    optional = [(n, configured.get(n, False)) for n in ("VOC", "CO₂")]
    if not any(ok for _, ok in optional):
        st.caption("VOC and CO₂ sensors are not configured on this unit, so no values are shown for them.")

    st.write("")
    with st.container(border=True):
        h1, h2 = st.columns([1.6, 1], vertical_alignment="center")
        with h1:
            ui.section("Particulate matter", "Inlet sensor · hover for exact values")
        with h2:
            rng = range_picker("la_range")
        charts.pm_trend(sn.history, sn.now, rng, s, key="la_pm", height=330)

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            charts.single_trend(sn.history, sn.now, rng, "temperature_c", "Temperature", "°C", "pm10", key="la_t")
    with c2:
        with st.container(border=True):
            charts.single_trend(sn.history, sn.now, rng, "humidity_pct", "Relative humidity", "%", "pm25", key="la_rh")

    c3, c4 = st.columns([1.2, 1])
    with c3:
        with st.container(border=True):
            ui.section("Sensor state", "Last-read time per channel")
            ts = pd.Timestamp(r.timestamp).strftime("%H:%M:%S")
            rows = [
                ("Inlet PM2.5 / PM10", live is not None, ts),
                ("Outlet PM2.5 / PM10", live is not None and live.outlet_pm25 is not None, ts),
                ("Temperature / RH", live is not None, ts),
            ]
            out = []
            for name, ok, t in rows:
                state = ui.status_html("Reporting", "good") if ok else ui.status_html("No data", "critical")
                out.append(f'<div class="ag-row"><div>{name}<small>Last read {t}'
                           f'</small></div>{state}</div>')
            for name in ("VOC", "CO₂"):
                out.append(f'<div class="ag-row"><div>{name}<small>No sensor fitted on this unit</small></div>'
                           f'{ui.status_html("Not configured", "neutral")}</div>')
            ui.render_html("".join(out))
    with c4:
        with st.container(border=True):
            ui.section("What these measurements mean")
            st.markdown(
                "- **PM2.5 / PM10** — mass concentration of airborne particles (µg/m³). The tower's filters act on these.\n"
                "- **VOC** — volatile organic compounds (gases such as solvents). A particle filter does not remove them; "
                "they need a separate sensor and, for removal, sorbent media.\n"
                "- **CO₂** — an indicator of ventilation and occupancy, not of particle pollution. Filtration does not lower CO₂.\n\n"
                "These quantities are independent: a low PM reading says nothing about VOC or CO₂, and vice versa.")
