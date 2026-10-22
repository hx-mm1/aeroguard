"""AeroGuard | Intelligent Environmental Monitoring System.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import time

import streamlit as st

from components import theme, ui
from services.runtime import init_state, tick
from views import camera, energy, live_air, maintenance, network, overview, performance, settings_page
from views.common import pollution_event_button

st.set_page_config(
    page_title="AeroGuard | Intelligent Environmental Monitoring System",
    page_icon=":material/air:",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_state(st.session_state)

theme.inject_css()

snap = tick(st.session_state)
st.session_state["snap"] = snap
st.session_state["last_run"] = time.time()

overview_page = st.Page(overview.render, title="Overview", icon=":material/dashboard:", url_path="overview",
                        default=True)
st.session_state["overview_page"] = overview_page
pages = [
    overview_page,
    st.Page(network.render, title="Malaysia Network", icon=":material/map:", url_path="network"),
    st.Page(live_air.render, title="Live Air Quality", icon=":material/air:", url_path="live-air"),
    st.Page(performance.render, title="Filtration Performance", icon=":material/filter_alt:", url_path="performance"),
    st.Page(energy.render, title="Energy & Sustainability", icon=":material/bolt:", url_path="energy"),
    st.Page(maintenance.render, title="Maintenance & Health", icon=":material/build:", url_path="maintenance"),
    st.Page(camera.render, title="Camera / Site Awareness", icon=":material/videocam:", url_path="camera"),
    st.Page(settings_page.render, title="Settings / Data Source", icon=":material/settings:", url_path="settings"),
]
page = st.navigation(pages, position="sidebar")

with st.sidebar:
    st.divider()
    st.caption("LIVE UPDATES")
    auto = st.toggle("Auto-refresh", value=True, key="auto_refresh",
                     help="Re-reads the data source every few seconds.")
    interval = st.select_slider("Interval (s)", [3, 5, 10, 30], value=5, key="refresh_s",
                                disabled=not auto)
    st.button("Refresh now", icon=":material/refresh:", width="stretch")
    pollution_event_button("sb_event")


@st.fragment(run_every=interval if auto else None)
def _auto_refresh() -> None:
    # The fragment timer fires every `interval` s; a full rerun pulls fresh data.
    # Skipped on Settings so a half-filled form is never interrupted.
    if auto and page.url_path != "settings" and time.time() - st.session_state.get("last_run", 0) >= interval - 0.5:
        st.rerun(scope="app")


_auto_refresh()

ui.header(snap)
st.write("")
page.run()
ui.footer(snap)
