"""Widgets shared by several pages (control panel, alerts, demo event)."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from components import ui
from services.calculations import fmt
from services.control import MODES
from services.runtime import change_mode
from services.sensors import supports_demo_controls

MODE_HELP = {
    "ECO": "Lower fan command when conditions allow (capped).",
    "AUTO": "Adjust fan command from smoothed PM2.5 using configurable bands.",
    "BOOST": "Request high fan operation within configured limits.",
}


def snap():
    return st.session_state["snap"]


def _set_mode(mode: str) -> None:
    if change_mode(st.session_state, mode, pd.Timestamp.now()):
        st.toast(f"Mode set to {mode}")


def _toggle_event() -> None:
    adapter = st.session_state["adapter"]
    store = st.session_state["store"]
    now = pd.Timestamp.now()
    if not supports_demo_controls(adapter):
        return
    if adapter.event_active:
        adapter.end_pollution_event(now)
        store.log(now, "Info", "Demo", "Pollution event ended — returning to normal conditions")
        st.toast("Event ended; readings will return to normal")
    else:
        adapter.start_pollution_event(now)
        store.log(now, "Warning", "Demo", "Pollution event started from demo controls")
        st.toast("Pollution event started")


def pollution_event_button(key: str, stretch: bool = True) -> None:
    adapter = st.session_state["adapter"]
    if not supports_demo_controls(adapter):
        return
    if adapter.event_active:
        st.button("End event · return to normal", key=key, on_click=_toggle_event,
                  width="stretch" if stretch else "content", icon=":material/restart_alt:")
    else:
        st.button("Simulate pollution event", key=key, on_click=_toggle_event, type="secondary",
                  width="stretch" if stretch else "content", icon=":material/cloud:",
                  help="Demo: injects a PM spike so you can watch AUTO respond.")


def control_panel(key_prefix: str = "ov") -> None:
    sn = snap()
    c, r, s = sn.controller, sn.reading, sn.settings
    ui.section("Filtration control", "Supervisory fan command")
    cols = st.columns(3)
    for col, mode in zip(cols, MODES):
        with col:
            st.button(mode, key=f"{key_prefix}_mode_{mode}", on_click=_set_mode, args=(mode,),
                      type="primary" if c.mode == mode else "secondary", width="stretch",
                      help=MODE_HELP[mode])
    pct = c.command_pct
    ui.render_html(f"""
<div style="display:flex;align-items:flex-end;justify-content:space-between;margin-top:12px">
  <div><div class="ag-kpi-label">Fan speed command</div>
       <div class="ag-big">{pct:.0f}<span class="unit">%</span></div></div>
  <div style="text-align:right"><div class="ag-kpi-label">Mode</div>
       <div style="font-weight:800;font-size:1.3rem;color:var(--ag-accent)">{c.mode}</div>
       <div class="ag-note">target {c.target_pct:.0f} %</div></div>
</div>
<div class="ag-bar"><div style="width:{pct:.0f}%"></div></div>
<div class="ag-reason">{html.escape(c.reason)}</div>
<div class="ag-mini">
  <div><div class="k">Airflow</div><div class="v">{fmt(None if sn.stale else r.airflow_m3h, 0, 'm³/h')}</div></div>
  <div><div class="k">Filter ΔP</div><div class="v">{fmt(None if sn.stale else r.filter_dp_pa, 0, 'Pa')}</div></div>
  <div><div class="k">Fan feedback</div><div class="v">{fmt(None if sn.stale else r.fan_feedback_pct, 0, '%')}</div></div>
  <div><div class="k">Smoothed PM2.5</div><div class="v">{fmt(c.smoothed_pm25, 1, 'µg/m³')}</div></div>
</div>
<div class="ag-note" style="margin-top:8px">Limits {s.hard_min_pct:.0f}–{s.hard_max_pct:.0f} % · ramp ≤ {s.ramp_pct_per_s:g} %/s ·
hysteresis {s.band_hysteresis:g} µg/m³. Motor protection stays in the hardware controller.</div>
""")


def alerts_panel(key_prefix: str, limit: int = 5) -> None:
    sn = snap()
    alerts = sn.open_alerts
    active_n = int((alerts["status"] == "Active").sum()) if not alerts.empty else 0
    ui.section("Active alerts", f"{len(alerts)} open · {active_n} unacknowledged")
    if alerts.empty:
        ui.render_html(f'<div class="ag-row">{ui.status_html("No open alerts", "good")}</div>')
        return
    for _, a in alerts.head(limit).iterrows():
        kind = ui.SEVERITY_KIND[a["severity"]]
        left, right = st.columns([5, 2], vertical_alignment="center")
        with left:
            ui.render_html(f'<div style="font-size:.84rem;color:var(--ag-text)">{ui.status_html(a["severity"], kind)} '
                           f'<span class="ag-note">· {pd.Timestamp(a["ts"]):%H:%M:%S} · {html.escape(a["source"])}</span><br>'
                           f'{html.escape(a["message"])}</div>')
        with right:
            if a["status"] == "Active":
                st.button("Acknowledge", key=f"{key_prefix}_ack_{a['id']}", width="stretch",
                          on_click=sn.store.acknowledge, args=(int(a["id"]), pd.Timestamp.now()))
            else:
                ui.render_html(f'<span class="ag-note">{ui.icon("good", 12)} Acknowledged</span>')
    if len(alerts) > limit:
        st.caption(f"+ {len(alerts) - limit} more — see Maintenance & System Health")


def range_picker(key: str, default: str = "24 h") -> str:
    val = st.segmented_control("Time range", ["1 h", "6 h", "24 h", "7 d"], default=default, key=key,
                               label_visibility="collapsed")
    return val or default
