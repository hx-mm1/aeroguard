"""A. Overview — the main summary dashboard."""

from __future__ import annotations

import streamlit as st

from components import charts, ui
from services.calculations import fmt
from views.common import alerts_panel, control_panel, pollution_event_button, range_picker, snap


def render() -> None:
    sn = snap()
    r, s, sim = sn.reading, sn.settings, sn.simulated
    live = None if sn.stale else r
    ui.demo_note(sn)

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        ui.aqi_card(sn.aqi, sim)
    with k2:
        label, kind = ui.pm_status(live and live.inlet_pm25, s)
        ui.kpi("PM2.5", live and live.inlet_pm25, "µg/m³", 1,
               f"{ui.status_html(label, kind)} <span class='ag-note'>· ref. {s.pm25_reference:.0f} (configurable)</span>",
               sim, sub="Inlet sensor · ambient air around the tower",
               tooltip="Fine particles ≤ 2.5 µm measured at the tower inlet.")
    with k3:
        label, kind = ui.pm10_status(live and live.inlet_pm10, s)
        ui.kpi("PM10", live and live.inlet_pm10, "µg/m³", 0,
               f"{ui.status_html(label, kind)} <span class='ag-note'>· ref. {s.pm10_reference:.0f} (configurable)</span>",
               sim, sub="Inlet sensor · ambient air around the tower",
               tooltip="Particles ≤ 10 µm measured at the tower inlet.")
    with k4:
        e = sn.eff_pm25
        foot = (ui.status_html("Paired inlet/outlet", "good") if e.ok and e.value >= 0
                else ui.status_html(e.message or "Not available", "neutral" if not e.ok else "warning"))
        ui.kpi("Removal efficiency", e.value, "%", 1, foot, sim,
               sub=f"PM2.5 single-pass · PM10: {fmt(sn.eff_pm10.value, 1, '%')}",
               tooltip="((inlet − outlet) / inlet) × 100 from paired readings across the filter. "
                       "Describes air passing through the tower, not the whole surrounding area.",
               bar_pct=e.value)

    st.write("")
    left, right = st.columns([2.05, 1])
    with left:
        with st.container(border=True):
            h1, h2 = st.columns([1.4, 1], vertical_alignment="center")
            with h1:
                ui.section("Air-quality trend", "Inlet PM2.5 and PM10 · dashed lines are configurable references")
            with h2:
                rng = range_picker("ov_range")
            charts.pm_trend(sn.history, sn.now, rng, s, key="ov_trend", height=345)
    with right:
        with st.container(border=True):
            control_panel("ov")
            pollution_event_button("ov_event")

    a, b, c = st.columns([1.25, 1, 1])
    with a:
        with st.container(border=True):
            ui.section("Filtration performance", "Before / after the filter, latest paired reading")
            charts.before_after(live or r, key="ov_ba", height=250)
            ui.render_html(f"""<div class="ag-mini">
<div><div class="k">PM2.5 removal</div><div class="v">{fmt(sn.eff_pm25.value, 1, '%')}</div></div>
<div><div class="k">PM10 removal</div><div class="v">{fmt(sn.eff_pm10.value, 1, '%')}</div></div>
<div><div class="k">CADR (PM2.5)</div><div class="v">{fmt(sn.cadr_pm25.value, 0, 'm³/h')}</div></div>
<div><div class="k">Clean air today</div><div class="v">{fmt(sn.clean_air_today.value, 0, 'm³')}</div></div>
</div>""")
    with b:
        with st.container(border=True):
            ui.section("System health", "Subsystem status")
            ui.render_html(ui.health_list(sn.health, sim))
    with c:
        with st.container(border=True):
            alerts_panel("ov", limit=4)

    with st.container(border=True):
        ui.section("Event log", "Most recent events and alerts · full history on the Maintenance page")
        ui.events_table(sn.store.events(limit=8), height=250)
