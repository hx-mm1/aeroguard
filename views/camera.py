"""F. Camera / Site Awareness."""

from __future__ import annotations

import streamlit as st

from components import ui
from views.common import snap

PLACEHOLDER_SVG = """<svg width="220" height="140" viewBox="0 0 220 140" aria-hidden="true">
<rect x="10" y="20" width="200" height="110" rx="10" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="6 6" opacity=".5"/>
<circle cx="110" cy="72" r="26" fill="none" stroke="currentColor" stroke-width="3" opacity=".7"/>
<circle cx="110" cy="72" r="11" fill="currentColor" opacity=".5"/>
<path d="M60 20l12-12h76l12 12" fill="none" stroke="currentColor" stroke-width="2" opacity=".5"/>
<path d="M40 112l140-80" stroke="currentColor" stroke-width="2" opacity=".35"/>
</svg>"""


def render() -> None:
    sn = snap()
    st.subheader("Camera / site awareness")
    cam = next((h for h in sn.health if h.name == "Camera"), None)

    a, b = st.columns([1.7, 1])
    with a:
        with st.container(border=True):
            ui.section("Camera view", "360° camera in the top assembly")
            ui.render_html(f"""
<div class="ag-placeholder">{PLACEHOLDER_SVG}
<div style="font-weight:700;color:var(--ag-text);font-size:1.05rem">Camera integration not configured</div>
<div>No video stream is connected to this dashboard. This panel is an illustration, <b>not a live feed</b>.</div>
<div class="ag-note">To integrate: provide an RTSP/HLS or snapshot endpoint from the camera's own NVR/VMS,
served over the site network with access control. Credentials must come from environment variables.</div>
</div>""")
    with b:
        with st.container(border=True):
            ui.section("Connectivity")
            state = cam.state if cam else "Not Configured"
            kind = ui.STATE_KIND.get(state, "neutral")
            ui.render_html(
                f'<div class="ag-row"><div>Camera heartbeat<small>{cam.detail if cam else ""}</small></div>'
                f'{ui.status_html(state, kind)}</div>'
                f'<div class="ag-row"><div>Video stream<small>No stream endpoint configured</small></div>'
                f'{ui.status_html("Not Configured", "neutral")}</div>'
                f'<div class="ag-row"><div>Recording<small>Disabled — nothing is stored</small></div>'
                f'{ui.status_html("Off", "neutral")}</div>'
)
        with st.container(border=True):
            ui.section("Purpose & limits")
            st.markdown(
                "- The camera supports **site awareness** (e.g. checking for obstruction of the intake, vandalism, "
                "or crowding near the unit).\n"
                "- It **does not measure air quality**; all air data come from the particle and climate sensors.")
        with st.container(border=True):
            ui.section("Privacy")
            st.markdown(
                "- **No facial recognition** or identification of individuals is implemented.\n"
                "- **No video is stored** unless recording is explicitly configured, justified, and signposted on site "
                "in line with applicable personal-data law (e.g. Malaysia's PDPA 2010).\n"
                "- Live viewing should be limited to authorised facilities staff.")
