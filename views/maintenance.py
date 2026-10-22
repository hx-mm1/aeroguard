"""E. Maintenance & System Health."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components import charts, ui
from components.schematic import tower_schematic
from services.calculations import fmt
from views.common import alerts_panel, range_picker, snap


def _filter_status(dp_n, s) -> tuple[str, str]:
    if dp_n is None:
        return "Not available", "neutral"
    if dp_n >= s.dp_replace_pa:
        return "Replace filter", "critical"
    if dp_n >= s.dp_warning_pa:
        return "Inspect filter", "warning"
    return "Filter OK", "good"


def render() -> None:
    sn = snap()
    r, s, sim = sn.reading, sn.settings, sn.simulated
    st.subheader("Maintenance & system health")

    dp_n = sn.dp_normalised
    label, kind = _filter_status(dp_n, s)
    est_left = s.filter_rated_hours - sn.filter_hours if sn.filter_hours is not None else None

    cols = st.columns(4)
    with cols[0]:
        ui.kpi("Filter ΔP (measured)", None if sn.stale else r.filter_dp_pa, "Pa", 0,
               f"<span class='ag-note'>At current airflow {fmt(None if sn.stale else r.airflow_m3h, 0, 'm³/h')}</span>", sim)
    with cols[1]:
        ui.kpi("ΔP at rated airflow", dp_n, "Pa", 0, ui.status_html(label, kind), sim,
               sub=f"Inspect ≥ {s.dp_warning_pa:.0f} Pa · replace ≥ {s.dp_replace_pa:.0f} Pa",
               bar_pct=None if dp_n is None else dp_n / s.dp_replace_pa * 100,
               tooltip="Measured ΔP scaled to rated airflow (ΔP ∝ flow^1.4) so filter loading can be compared "
                       "across fan speeds. This is the primary filter-loading indicator.")
    with cols[2]:
        ui.kpi("Operating hours", sn.operating_hours, "h", 0,
               f"<span class='ag-note'>Filter in service {fmt(sn.filter_hours, 0, 'h')}</span>", sim)
    with cols[3]:
        ui.kpi("Rough filter-life estimate", est_left, "h left", 0,
               ui.status_html("Rough estimate only", "neutral"), sim,
               sub=f"From a configurable {s.filter_rated_hours:,.0f} h rating. ΔP decides replacement, not hours.")

    st.write("")
    a, b = st.columns([1.6, 1])
    with a:
        with st.container(border=True):
            h1, h2 = st.columns([1.4, 1], vertical_alignment="center")
            with h1:
                ui.section("Filter differential pressure", "Thresholds are configurable in Settings")
            with h2:
                rng = range_picker("mt_range", default="7 d")
            charts.dp_trend(sn.history, sn.now, rng, s, key="mt_dp", height=300)
    with b:
        with st.container(border=True):
            ui.section("Component status")
            ui.render_html(ui.health_list(sn.health, sim))

    c, d = st.columns([1, 1.6])
    with c:
        with st.container(border=True):
            alerts_panel("mt", limit=8)
            if not sn.open_alerts.empty and (sn.open_alerts["status"] == "Active").any():
                st.button("Acknowledge all", key="mt_ack_all", on_click=sn.store.acknowledge_all,
                          args=(pd.Timestamp.now(),))
        with st.container(border=True):
            ui.section("Tower layout", "Service door gives access to both filter stages and the electronics")
            live = None if sn.stale else r
            cam = next((h for h in sn.health if h.name == "Camera"), None)
            ui.render_html(tower_schematic({
                "camera": cam.state if cam else "—",
                "display": f"{sn.controller.mode} · {sn.controller.command_pct:.0f} %",
                "prefilter": "Cleaned 14 days ago",
                "inlet": f"PM2.5 {fmt(live and live.inlet_pm25, 1)} · PM10 {fmt(live and live.inlet_pm10, 0)} µg/m³",
                "network": "Link down" if sn.stale else "Connected",
                "outlet": f"PM2.5 {fmt(live and live.outlet_pm25, 1, 'µg/m³')}",
                "fan": f"{fmt(live and live.fan_feedback_pct, 0, '%')} · {fmt(live and live.power_w, 0, 'W')}",
                "filter": f"ΔP {fmt(dp_n, 0, 'Pa')} · {label}",
                "door": f"Filter in service {fmt(sn.filter_hours, 0, 'h')}",
                "removal": fmt(sn.eff_pm25.value, 1, "% PM2.5"),
            }, title=f"{s.tower_id} · TECHNICAL VIEW"))
    with d:
        with st.container(border=True):
            ui.section("Maintenance history")
            m = sn.store.maintenance()
            if m.empty:
                st.info("No maintenance records.")
            else:
                st.dataframe(pd.DataFrame({
                    "Date": pd.to_datetime(m["ts"]).dt.strftime("%d %b %Y"),
                    "Action": m["action"], "Detail": m["detail"], "By": m["performed_by"],
                    "Record": m["simulated"].map({1: "Demo record", 0: "Operator entry"}),
                }), hide_index=True, width="stretch", height=230)
            with st.expander("Log a maintenance action"):
                with st.form("mt_form", clear_on_submit=True):
                    action = st.selectbox("Action", ["Filter inspected", "Pre-filter cleaned", "Main filter replaced",
                                                     "Sensor calibration check", "Fan inspection", "Other"])
                    detail = st.text_input("Detail", max_chars=200)
                    by = st.text_input("Performed by", max_chars=60)
                    if st.form_submit_button("Save record", type="primary"):
                        sn.store.add_maintenance(pd.Timestamp.now(), action, detail.strip(), by.strip() or "Operator", False)
                        sn.store.log(pd.Timestamp.now(), "Info", "Maintenance", f"Maintenance logged: {action}",
                                     simulated=False)
                        st.success("Record saved.")
        with st.container(border=True):
            ui.section("Alert & event history")
            sev = st.multiselect("Severity", ["Info", "Warning", "Critical"], default=["Info", "Warning", "Critical"],
                                 key="mt_sev", label_visibility="collapsed")
            ev = sn.store.events(limit=500)
            ui.events_table(ev[ev["severity"].isin(sev)], height=320)
