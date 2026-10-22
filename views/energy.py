"""D. Energy & Sustainability."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components import charts, ui
from services.calculations import fmt, specific_energy_wh_per_1000m3
from views.common import range_picker, snap


def render() -> None:
    sn = snap()
    r, sim = sn.reading, sn.simulated
    live = None if sn.stale else r
    st.subheader("Energy & sustainability")

    hours_today = (sn.now - sn.now.normalize()).total_seconds() / 3600
    e_today = sn.energy_today.value
    per_hour = e_today / hours_today if e_today is not None and hours_today > 0.05 else None
    spec = specific_energy_wh_per_1000m3(e_today, sn.clean_air_today.value)

    cols = st.columns(4)
    with cols[0]:
        ui.kpi("Instantaneous power", live and live.power_w, "W", 0,
               "<span class='ag-note'>Fan + electronics + camera</span>", sim)
    with cols[1]:
        ui.kpi("Energy today", e_today, "kWh", 2,
               f"<span class='ag-note'>Since 00:00 · {sn.energy_today.message or 'integrated from power samples'}</span>", sim)
    with cols[2]:
        ui.kpi("Energy per operating hour", per_hour, "kWh/h", 3,
               "<span class='ag-note'>Today's energy ÷ hours run today</span>", sim)
    with cols[3]:
        ui.kpi("Energy per clean air", spec.value, "Wh / 1,000 m³", 1,
               "<span class='ag-note'>Today's energy ÷ PM2.5 clean-air volume</span>" if spec.ok
               else ui.status_html(spec.message, "neutral"), sim,
               tooltip="Wh used per 1,000 m³ of particle-free-equivalent air (CADR integrated over time).")

    st.write("")
    a, b = st.columns([1.5, 1])
    with a:
        with st.container(border=True):
            h1, h2 = st.columns([1.4, 1], vertical_alignment="center")
            with h1:
                ui.section("Power over time")
            with h2:
                rng = range_picker("en_range")
            charts.power_trend(sn.history, sn.now, rng, key="en_power")
    with b:
        with st.container(border=True):
            ui.section("Daily energy", "Partial days are labelled")
            hist = sn.history[sn.history["timestamp"] >= sn.now.normalize() - pd.Timedelta(days=6)]
            charts.daily_energy(hist, key="en_daily")

    with st.container(border=True):
        ui.section("Notes on sustainability claims")
        st.markdown(
            "- Energy is integrated from power samples with the trapezoidal rule; gaps longer than 5 minutes are not "
            "filled in, so a day with missing data is under-counted and is labelled *partial*.\n"
            "- Fan power rises roughly with the cube of speed, so ECO mode and AUTO's low band save most energy "
            "when air is clean.\n"
            "- **No CO₂-emissions-saved figure is shown.** Reporting one would require a disclosed grid emissions "
            "factor (kg CO₂e/kWh for the relevant grid and year) and a defined baseline to compare against.")
