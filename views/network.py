"""H. Malaysia Network — the demo fleet on a map, with regional controls."""

from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import ui
from components.schematic import tower_schematic
from components.theme import PLOTLY_CONFIG, STATUS, current_theme, tok
from services.calculations import fmt
from services.control import MODES
from services.fleet import ATTENTION, OFFLINE, ONLINE, REGIONS, fleet_status, pm_level
from services.runtime import change_mode
from services.sensors import OFFLINE as HEALTH_OFFLINE
from views.common import snap

PM_COLORS = {"Low": STATUS["good"], "Elevated": STATUS["warning"], "High": STATUS["serious"],
             "Severe": STATUS["critical"], "No data": STATUS["neutral"]}
STATUS_COLORS = {ONLINE: STATUS["good"], ATTENTION: STATUS["warning"], OFFLINE: STATUS["critical"]}


def _mode_colors() -> dict:
    t = tok()
    return {"AUTO": t["pm25"], "ECO": t["outlet"], "BOOST": t["series3"], "Offline": STATUS["neutral"]}


def _live_row(sn) -> dict:
    """AG-001 mirrors the main dashboard's tower."""
    r, c = sn.reading, sn.controller
    if sn.stale:
        return {"site": sn.settings.site_name, "status": OFFLINE, "note": "No recent data", "mode": c.mode,
                "pm25": None, "pm10": None, "fan_pct": None, "efficiency": None, "airflow": None,
                "power_w": None, "dp_pa": None}
    crit = (not sn.open_alerts.empty) and (sn.open_alerts["severity"] == "Critical").any()
    offline_parts = [h.name for h in sn.health if h.state == HEALTH_OFFLINE]
    status = ATTENTION if crit or offline_parts else ONLINE
    note = ("Critical alert open" if crit else
            (f"{offline_parts[0]} offline" if offline_parts else "All systems normal"))
    return {"site": sn.settings.site_name, "status": status, "note": note, "mode": c.mode,
            "pm25": r.inlet_pm25, "pm10": r.inlet_pm10, "fan_pct": round(c.command_pct),
            "efficiency": sn.eff_pm25.value, "airflow": r.airflow_m3h, "power_w": r.power_w,
            "dp_pa": round(sn.dp_normalised) if sn.dp_normalised else None}


def _apply_region(region: str, mode: str, df: pd.DataFrame) -> None:
    state = st.session_state
    modes = state.setdefault("fleet_modes", {})
    targets = df[(df["region"] == region) & (df["status"] != OFFLINE)]["tower_id"].tolist()
    for tid in targets:
        if tid == "AG-001":
            change_mode(state, mode, pd.Timestamp.now())
        else:
            modes[tid] = mode
    state["store"].log(pd.Timestamp.now(), "Info", "Fleet",
                       f"{mode} applied to {region} region ({len(targets)} towers online)")
    st.toast(f"{mode} applied to {len(targets)} towers in {region}")


def _toggle_haze(region: str) -> None:
    haze = st.session_state.setdefault("fleet_haze", set())
    if region in haze:
        haze.discard(region)
        msg = f"Haze scenario cleared over {region} region"
    else:
        haze.add(region)
        msg = f"Haze scenario started over {region} region"
    st.session_state["store"].log(pd.Timestamp.now(), "Warning" if region in haze else "Info", "Fleet", msg)
    st.toast(msg)


def _map(df: pd.DataFrame, color_by: str, selected: str) -> go.Figure:
    t = tok()
    s = snap().settings
    fig = go.Figure()
    if color_by == "Air quality":
        key = df["pm25"].map(lambda v: pm_level(v, s))
        palette = PM_COLORS
    elif color_by == "Status":
        key, palette = df["status"], STATUS_COLORS
    else:
        key = df.apply(lambda r: "Offline" if r["status"] == OFFLINE else r["mode"], axis=1)
        palette = _mode_colors()
    sel = df[df["tower_id"] == selected]
    if not sel.empty:
        fig.add_trace(go.Scattermap(lat=sel["lat"], lon=sel["lon"], mode="markers", hoverinfo="skip",
                                    marker=dict(size=34, color=t["accent"], opacity=0.28), showlegend=False))
    for name, color in palette.items():
        d = df[key == name]
        if d.empty:
            continue
        hover = [
            f"<b>{r.tower_id}</b> · {html.escape(r.site)}<br>{r.city}, {r.state}<br>"
            f"PM2.5 {fmt(r.pm25, 1, 'µg/m³', na='n/a')} · {r.status}<br>Mode {r.mode} · fan {fmt(r.fan_pct, 0, '%', na='n/a')}"
            for r in d.itertuples()]
        fig.add_trace(go.Scattermap(
            lat=d["lat"], lon=d["lon"], mode="markers+text", name=name,
            marker=dict(size=15, color=color, opacity=0.95),
            text=d["tower_id"], textposition="top right",
            textfont=dict(size=10, color=t["text2"]),
            customdata=d[["tower_id"]].to_numpy(), hovertext=hover, hovertemplate="%{hovertext}<extra></extra>"))
    fig.update_layout(
        map=dict(style="carto-darkmatter" if current_theme() == "dark" else "carto-positron",
                 center=dict(lat=4.0, lon=108.9), zoom=4.0),  # MapLibre zoom (512-px tiles): fits Peninsula + Borneo
        height=560, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", x=0.01, y=0.99, bgcolor=t["surface"], bordercolor=t["border"], borderwidth=1,
                    font=dict(color=t["text2"], size=11), title=dict(text=f"{color_by}  ", font=dict(color=t["text"]))),
        hoverlabel=dict(bgcolor=t["surface"], bordercolor=t["border"], font=dict(color=t["text"])),
        uirevision="fleet-map", clickmode="event+select")
    return fig


def _tower_values(row) -> dict:
    off = row["status"] == OFFLINE
    na = "No data" if off else "—"
    return {
        "camera": na if off else "Heartbeat OK",
        "display": na if off else f"{row['mode']} · {fmt(row['fan_pct'], 0, '%')}",
        "prefilter": na if off else "Captures coarse dust, PM10",
        "inlet": na if off else f"PM2.5 {fmt(row['pm25'], 1)} · PM10 {fmt(row['pm10'], 0)} µg/m³",
        "network": "Link down" if off else "Connected",
        "outlet": na if off else f"{fmt(row['airflow'], 0, 'm³/h')} clean air",
        "fan": na if off else f"{fmt(row['fan_pct'], 0, '%')} command · {fmt(row['power_w'], 0, 'W')}",
        "filter": na if off else f"ΔP {fmt(row['dp_pa'], 0, 'Pa')} at rated flow",
        "door": "Filter & electronics access",
        "removal": na if off else f"{fmt(row['efficiency'], 1, '%')} PM2.5",
    }


def render() -> None:
    sn = snap()
    s = sn.settings
    state = st.session_state
    ui.watermark()
    st.subheader("Malaysia network")
    st.caption("AeroGuard towers deployed nationwide · click a tower on the map or pick it from the list")

    df = fleet_status(sn.now, s, state.setdefault("fleet_modes", {}), state.setdefault("fleet_haze", set()),
                      _live_row(sn))

    online = df[df["status"] != OFFLINE]
    totals = [
        ("Towers deployed", f"{len(df)}"),
        ("Online", f"{(df['status'] != OFFLINE).sum()} / {len(df)}"),
        ("Needs attention", f"{(df['status'] != ONLINE).sum()}"),
        ("Average PM2.5", fmt(online["pm25"].mean(), 1, "µg/m³")),
        ("Clean air today", fmt(online["clean_air_today_m3"].sum() / 1e6, 2, "million m³")),
        ("Energy today", fmt(online["energy_today_kwh"].sum(), 0, "kWh")),
    ]
    ui.render_html('<div class="ag-footer" style="grid-template-columns:repeat(6,minmax(0,1fr));margin-top:4px">'
                   + "".join(f'<div><div class="k">{k}</div><div class="v">{v}</div></div>' for k, v in totals)
                   + "</div>")
    st.write("")

    f1, f2, f3 = st.columns([1.3, 1.3, 1.2], vertical_alignment="bottom")
    regions = f1.multiselect("Region", REGIONS, default=REGIONS, key="fleet_regions")
    statuses = f2.multiselect("Status", [ONLINE, ATTENTION, OFFLINE], default=[ONLINE, ATTENTION, OFFLINE],
                              key="fleet_statuses")
    color_by = f3.segmented_control("Colour by", ["Air quality", "Status", "Mode"], default="Air quality",
                                    key="fleet_color") or "Air quality"
    view = df[df["region"].isin(regions) & df["status"].isin(statuses)]

    ids = df["tower_id"].tolist()
    state.setdefault("fleet_pick", "AG-001")

    left, right = st.columns([1.65, 1])
    with left:
        with st.container(border=True):
            event = st.plotly_chart(_map(view, color_by, state["fleet_pick"]), width="stretch",
                                    config={**PLOTLY_CONFIG, "scrollZoom": False}, key="fleet_map",
                                    on_select="rerun", selection_mode="points")
            points = (event or {}).get("selection", {}).get("points", []) if event else []
            if points:
                cd = points[0].get("customdata")
                picked = cd[0] if isinstance(cd, (list, tuple)) and cd else None
                if picked and picked in ids and picked != state.get("fleet_last_click"):
                    state["fleet_last_click"] = picked
                    state["fleet_pick"] = picked
                    st.rerun()
            ui.render_html('<div class="ag-note">Map data © OpenStreetMap contributors © CARTO · drag to pan, zoom with the toolbar</div>')

    with right:
        with st.container(border=True):
            labels = {r.tower_id: f"{r.tower_id} · {r.site}" for r in df.itertuples()}
            pick = st.selectbox("Tower", ids, key="fleet_pick", format_func=lambda i: labels[i])
            row = df[df["tower_id"] == pick].iloc[0]
            kind = {ONLINE: "good", ATTENTION: "warning", OFFLINE: "critical"}[row["status"]]
            level = pm_level(row["pm25"], s)
            ui.render_html(f"""
<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-top:4px">
  <div><div style="font-weight:800;font-size:1.15rem;color:var(--ag-text)">{html.escape(row['site'])}</div>
  <div class="ag-note">{html.escape(row['city'])}, {html.escape(row['state'])} · {html.escape(row['setting'])}</div></div>
  {ui.status_html(row['status'], kind)}
</div>
<div class="ag-note" style="margin-top:4px">{html.escape(row['note'])}</div>
<div class="ag-mini">
  <div><div class="k">PM2.5</div><div class="v">{fmt(row['pm25'], 1, 'µg/m³')}</div></div>
  <div><div class="k">Air quality</div><div class="v">{level}</div></div>
  <div><div class="k">Mode · fan</div><div class="v">{row['mode']} · {fmt(row['fan_pct'], 0, '%')}</div></div>
  <div><div class="k">Removal</div><div class="v">{fmt(row['efficiency'], 1, '%')}</div></div>
</div>""")
            ui.render_html(tower_schematic(_tower_values(row), title=f"{row['tower_id']} · TECHNICAL VIEW"))
            if pick == "AG-001":
                st.page_link(st.session_state["overview_page"], label="Open full live dashboard",
                             icon=":material/open_in_new:")

    a, b = st.columns([1, 1.4])
    with a:
        with st.container(border=True):
            ui.section("Regional control", "Send a mode to every online tower in a region")
            region = st.selectbox("Region", REGIONS, key="fleet_ctrl_region")
            in_region = df[df["region"] == region]
            st.caption(f"{len(in_region)} towers · {(in_region['status'] != OFFLINE).sum()} online · "
                       f"modes now: " + ", ".join(f"{m} {n}" for m, n in in_region['mode'].value_counts().items()))
            cols = st.columns(3)
            for col, mode in zip(cols, MODES):
                col.button(mode, key=f"fleet_mode_{mode}", on_click=_apply_region, args=(region, mode, df),
                           width="stretch")
            hazy = region in state["fleet_haze"]
            st.button(("End haze scenario" if hazy else "Simulate regional haze") + f" · {region}",
                      key="fleet_haze_btn", on_click=_toggle_haze, args=(region,), width="stretch",
                      icon=":material/restart_alt:" if hazy else ":material/foggy:",
                      help="Demo: raises PM2.5 across the region so you can watch every tower respond.")
    with b:
        with st.container(border=True):
            ui.section("Towers", f"{len(view)} shown")
            table = pd.DataFrame({
                "Tower": view["tower_id"], "Site": view["site"], "State": view["state"],
                "Status": view["status"], "PM2.5 (µg/m³)": view["pm25"], "Mode": view["mode"],
                "Fan (%)": view["fan_pct"], "Removal (%)": view["efficiency"],
            })
            st.dataframe(table, hide_index=True, width="stretch", height=300,
                         column_config={"PM2.5 (µg/m³)": st.column_config.NumberColumn(format="%.1f"),
                                        "Removal (%)": st.column_config.NumberColumn(format="%.1f")})
