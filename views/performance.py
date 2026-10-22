"""C. Filtration Performance — removal efficiency, CADR and caveats."""

from __future__ import annotations

import streamlit as st

from components import charts, ui
from services.calculations import fmt
from views.common import range_picker, snap


def render() -> None:
    sn = snap()
    r, s, sim = sn.reading, sn.settings, sn.simulated
    live = None if sn.stale else r
    st.subheader("Filtration performance")

    cols = st.columns(4)
    with cols[0]:
        ui.kpi("Inlet PM2.5 → outlet", live and live.inlet_pm25, "µg/m³", 1,
               f"Outlet <b>{fmt(live and live.outlet_pm25, 1, 'µg/m³')}</b>", sim)
    with cols[1]:
        ui.kpi("Inlet PM10 → outlet", live and live.inlet_pm10, "µg/m³", 0,
               f"Outlet <b>{fmt(live and live.outlet_pm10, 1, 'µg/m³')}</b>", sim)
    with cols[2]:
        e25, e10 = sn.eff_pm25, sn.eff_pm10
        foot = ui.status_html(e25.message, "warning") if e25.message else f"PM10: <b>{fmt(e10.value, 1, '%')}</b>"
        ui.kpi("PM2.5 removal efficiency", e25.value, "%", 1, foot, sim, bar_pct=e25.value)
    with cols[3]:
        c = sn.cadr_pm25
        ui.kpi("CADR (PM2.5)", c.value, "m³/h", 0,
               f"Airflow {fmt(live and live.airflow_m3h, 0, 'm³/h')}" if c.ok else ui.status_html(c.message, "neutral"),
               sim, sub=f"Clean air delivered today: {fmt(sn.clean_air_today.value, 0, 'm³')}",
               tooltip="Simplified single-pollutant CADR = airflow × fractional removal efficiency.")

    st.write("")
    a, b = st.columns([1, 1.6])
    with a:
        with st.container(border=True):
            ui.section("Before / after", "Latest paired reading")
            charts.before_after(live or r, key="pf_ba", height=300)
    with b:
        with st.container(border=True):
            h1, h2 = st.columns([1.4, 1], vertical_alignment="center")
            with h1:
                ui.section("Removal efficiency history", "Averaged per interval · gaps = invalid or missing pairs")
            with h2:
                rng = range_picker("pf_range", default="7 d")
            charts.efficiency_trend(sn.history, sn.now, rng, s, key="pf_eff", height=300)

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            ui.section("Airflow")
            charts.airflow_trend(sn.history, sn.now, rng, key="pf_air")
    with c2:
        with st.container(border=True):
            ui.section("Fan command vs feedback")
            charts.fan_trend(sn.history, sn.now, rng, key="pf_fan")

    with st.container(border=True):
        ui.section("Method, assumptions and caveats")
        ui.render_html(
            '<div class="ag-formula">removal_efficiency_% = (inlet − outlet) / inlet × 100</div>'
            '<div style="height:6px"></div>'
            '<div class="ag-formula">CADR [m³/h] = airflow [m³/h] × removal_efficiency_% / 100</div>')
        st.markdown(f"""
- Efficiency is a **single-pass** figure for air moving through the tower. It does **not** mean the surrounding area
  is cleaner by the same percentage — that depends on space volume, ventilation, wind and the number of units.
- Results are only meaningful when inlet and outlet sensors are the **same model, co-located for calibration**, and
  sampling at the same time. Calibrate them side by side before trusting small differences.
- Efficiency is not calculated when either reading is missing, negative, or when inlet PM is below
  **{s.min_inlet_for_efficiency:g} µg/m³** (sensor noise would dominate). An outlet higher than the inlet is shown as a
  negative value and flagged, not hidden.
- CADR is only calculated with a valid airflow and an efficiency between 0 and 100 %. It is rounded to 10 m³/h to
  avoid false precision. A standardised CADR test (e.g. in a test chamber) would be needed for a certified rating.
""")
