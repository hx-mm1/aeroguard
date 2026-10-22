"""G. Settings / Data Source."""

from __future__ import annotations

from dataclasses import asdict, fields, replace

import pandas as pd
import streamlit as st

from components import ui
from services.sensors import supports_demo_controls
from views.common import snap

FAULTS = {
    "outlet_sensor": ("Outlet PM sensor offline", "Removal efficiency and CADR switch to “Not available”."),
    "camera": ("Camera disconnected", "Raises a camera alert."),
    "data_link": ("Data link lost", "Readings stop; the dashboard shows stale/offline after the configured timeout."),
}


def _apply(new) -> None:
    """Copy validated values into the live Settings object (shared with the adapter)."""
    cur = st.session_state["settings"]
    for f in fields(cur):
        setattr(cur, f.name, getattr(new, f.name))


def _toggle_fault(key: str) -> None:
    adapter = st.session_state["adapter"]
    on = st.session_state[f"fault_{key}"]
    adapter.faults[key] = on
    st.session_state["store"].log(pd.Timestamp.now(), "Info", "Demo",
                                  f"Simulated fault {'injected' if on else 'cleared'}: {FAULTS[key][0]}")


def _reset_demo() -> None:
    st.session_state["store"].reset()
    for k in ("adapter", "store", "controller", "last_tick"):
        st.session_state.pop(k, None)
    for k in FAULTS:
        st.session_state.pop(f"fault_{k}", None)
    st.toast("Demo data regenerated")


def render() -> None:
    sn = snap()
    s = sn.settings
    st.subheader("Settings & data source")

    a, b = st.columns([1, 1])
    with a:
        with st.container(border=True):
            ui.section("Data source")
            st.radio("Adapter", ["Demo simulator (active)", "Serial / ESP32 — not connected",
                                 "MQTT — not connected"], index=0, disabled=True, key="ds_radio",
                     help="Real adapters are added in code (see README → Connecting real sensors).")
            ui.render_html(
                f'<div class="ag-row"><div>Current adapter<small>{sn.adapter.description}</small></div>'
                f'{ui.status_html("DEMO MODE" if sn.simulated else "LIVE", "warning" if sn.simulated else "good")}</div>')
            st.caption("Credentials such as broker passwords are never entered here or written to logs. A real "
                       "adapter reads them from environment variables on the server.")
            ui.section("Configured channels")
            rows = "".join(
                f'<div class="ag-row"><div>{name}</div>'
                f'{ui.status_html("Configured" if ok else "Not Configured", "good" if ok else "neutral")}</div>'
                for name, ok in sn.adapter.channels().items())
            ui.render_html(rows)

    with b:
        if supports_demo_controls(sn.adapter):
            with st.container(border=True):
                ui.section("Demo controls", "For demonstrations only — every effect is simulated and logged")
                from views.common import pollution_event_button
                pollution_event_button("st_event", stretch=False)
                for key, (label, help_text) in FAULTS.items():
                    st.toggle(f"Simulate: {label}", value=sn.adapter.faults[key], key=f"fault_{key}",
                              help=help_text, on_change=_toggle_fault, args=(key,))
                st.button("Reset demo data", on_click=_reset_demo, icon=":material/restart_alt:",
                          help="Regenerates simulated history and clears the event log.")
        with st.container(border=True):
            ui.section("Display")
            st.markdown("Switch between **Light (product)** and **Control room (dark)** from the "
                        "**⋮ menu (top right) → Settings → Choose app theme**. The choice applies to "
                        "your browser only.")

    with st.form("settings_form"):
        ui.section("Tower & thresholds", "Changes apply to this session; “Save as default” also writes data/settings.json")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Identity**")
            tower_id = st.text_input("Tower ID", s.tower_id, max_chars=20)
            site = st.text_input("Site / location", s.site_name, max_chars=60)
            st.markdown("**Reference lines (configurable, not health limits)**")
            pm25_ref = st.number_input("PM2.5 reference (µg/m³)", 1.0, 500.0, float(s.pm25_reference), 1.0)
            pm10_ref = st.number_input("PM10 reference (µg/m³)", 1.0, 1000.0, float(s.pm10_reference), 5.0)
        with c2:
            st.markdown("**AUTO control bands (smoothed PM2.5, µg/m³)**")
            low = st.number_input("Low → Elevated", 1.0, 500.0, float(s.pm25_low), 1.0)
            high = st.number_input("Elevated → High", 1.0, 500.0, float(s.pm25_high), 1.0)
            crit = st.number_input("High → Severe", 1.0, 500.0, float(s.pm25_critical), 1.0)
            hyst = st.number_input("Hysteresis (µg/m³)", 0.0, 50.0, float(s.band_hysteresis), 0.5)
            tau = st.number_input("Smoothing time constant (s)", 1.0, 600.0, float(s.smoothing_tau_s), 5.0)
        with c3:
            st.markdown("**Fan command limits (%)**")
            hmin, hmax = st.slider("Hard limits", 0, 100, (int(s.hard_min_pct), int(s.hard_max_pct)))
            amin, amax = st.slider("AUTO range", 0, 100, (int(s.auto_min_pct), int(s.auto_max_pct)))
            eco = st.slider("ECO cap", 0, 100, int(s.eco_cap_pct))
            boost = st.slider("BOOST level", 0, 100, int(s.boost_pct))
            ramp = st.number_input("Max ramp (%/s)", 0.1, 20.0, float(s.ramp_pct_per_s), 0.1)
        c4, c5, _ = st.columns(3)
        with c4:
            st.markdown("**Filter**")
            dpw = st.number_input("ΔP inspect (Pa, at rated airflow)", 10.0, 2000.0, float(s.dp_warning_pa), 5.0)
            dpr = st.number_input("ΔP replace (Pa, at rated airflow)", 10.0, 2000.0, float(s.dp_replace_pa), 5.0)
            rated_h = st.number_input("Rough filter rating (h)", 100.0, 50000.0, float(s.filter_rated_hours), 100.0)
        with c5:
            st.markdown("**Data quality**")
            stale = st.number_input("Stale after (s)", 10, 3600, int(s.stale_after_s), 10)
            min_in = st.number_input("Min. inlet PM for efficiency (µg/m³)", 0.0, 50.0,
                                     float(s.min_inlet_for_efficiency), 0.5)
        save_c1, save_c2, _ = st.columns([1, 1, 3])
        apply_btn = save_c1.form_submit_button("Apply", type="primary", width="stretch")
        default_btn = save_c2.form_submit_button("Save as default", width="stretch")

    if apply_btn or default_btn:
        cand = replace(s, tower_id=tower_id.strip() or s.tower_id, site_name=site.strip() or s.site_name,
                       pm25_reference=pm25_ref, pm10_reference=pm10_ref, pm25_low=low, pm25_high=high,
                       pm25_critical=crit, band_hysteresis=hyst, smoothing_tau_s=tau,
                       hard_min_pct=float(hmin), hard_max_pct=float(hmax), auto_min_pct=float(amin),
                       auto_max_pct=float(amax), eco_cap_pct=float(eco), boost_pct=float(boost),
                       ramp_pct_per_s=ramp, dp_warning_pa=dpw, dp_replace_pa=dpr, filter_rated_hours=rated_h,
                       stale_after_s=int(stale), min_inlet_for_efficiency=min_in)
        problems = cand.validate()
        if problems:
            st.error("Settings not applied:\n\n" + "\n".join(f"- {p}" for p in problems))
        else:
            changed = [k for k, v in asdict(cand).items() if getattr(s, k) != v]
            _apply(cand)
            if default_btn:
                s.save()
            sn.store.log(pd.Timestamp.now(), "Info", "Settings",
                         f"Settings updated ({', '.join(changed) or 'no changes'})"
                         + ("; saved as default" if default_btn else ""), simulated=False)
            st.toast("Settings applied" + (" and saved as default." if default_btn else "."))
            st.rerun()
