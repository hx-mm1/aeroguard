"""Plotly charts. One y-axis per chart; measures of different scale get their own chart."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.theme import PLOTLY_CONFIG, plotly_layout, tok
from services.calculations import efficiency_series, energy_kwh, is_valid_number, normalised_dp

RANGES = {"1 h": (pd.Timedelta(hours=1), None), "6 h": (pd.Timedelta(hours=6), None),
          "24 h": (pd.Timedelta(hours=24), "5min"), "7 d": (pd.Timedelta(days=7), "30min")}


def window(df: pd.DataFrame, now, label: str) -> pd.DataFrame:
    """Slice history to a range and downsample long ranges (mean per bucket)."""
    span, rule = RANGES[label]
    d = df[df["timestamp"] >= pd.Timestamp(now) - span]
    if rule and not d.empty:
        num = d.drop(columns=["mode"]).set_index("timestamp")
        d = num.resample(rule).mean().reset_index()
    return d


def show(fig: go.Figure, key: str) -> None:
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key=key)


def _line(fig, x, y, name, color, unit, dash=None, width=2):
    fig.add_trace(go.Scatter(x=x, y=y, name=name, mode="lines", line=dict(color=color, width=width, dash=dash),
                             connectgaps=False, hovertemplate=f"%{{y:.1f}} {unit}<extra>{name}</extra>"))


def _ref_line(fig, y, text):
    t = tok()
    fig.add_hline(y=y, line=dict(color=t["ref"], width=1, dash="dash"),
                  annotation_text=text, annotation_position="top right",
                  annotation_font=dict(size=10, color=t["muted"]))


def pm_trend(df, now, label, s, key, height=330, refs=True) -> None:
    t = tok()
    d = window(df, now, label)
    fig = go.Figure()
    _line(fig, d["timestamp"], d["inlet_pm25"], "PM2.5 (inlet)", t["pm25"], "µg/m³")
    _line(fig, d["timestamp"], d["inlet_pm10"], "PM10 (inlet)", t["pm10"], "µg/m³")
    if refs:
        _ref_line(fig, s.pm25_reference, f"PM2.5 reference {s.pm25_reference:.0f} (configurable)")
        _ref_line(fig, s.pm10_reference, f"PM10 reference {s.pm10_reference:.0f} (configurable)")
    fig.update_layout(**plotly_layout(height))
    fig.update_yaxes(title_text="Concentration (µg/m³)", rangemode="tozero")
    show(fig, key)


def single_trend(df, now, label, col, name, unit, color_key, key, height=240, decimals=1, refs=()) -> None:
    t = tok()
    d = window(df, now, label)
    fig = go.Figure()
    _line(fig, d["timestamp"], d[col], name, t[color_key], unit)
    for y, text in refs:
        _ref_line(fig, y, text)
    fig.update_layout(**plotly_layout(height, showlegend=False,
                                      title=dict(text=f"{name} ({unit})", font=dict(size=13, color=t["text"]), x=0, y=.98)))
    show(fig, key)


def before_after(reading, key, height=280) -> None:
    t = tok()
    pollutants = ["PM2.5", "PM10"]
    inlet = [reading.inlet_pm25, reading.inlet_pm10]
    outlet = [reading.outlet_pm25, reading.outlet_pm10]
    fig = go.Figure()
    for name, vals, color in (("Inlet (before)", inlet, t["inlet"]), ("Outlet (after)", outlet, t["outlet"])):
        clean = [v if is_valid_number(v) else None for v in vals]
        fig.add_trace(go.Bar(
            x=pollutants, y=clean, name=name, marker=dict(color=color, cornerradius=4),
            text=[f"{v:.1f}" if v is not None else "n/a" for v in clean], textposition="outside",
            textfont=dict(color=t["text2"]), hovertemplate="%{y:.1f} µg/m³<extra>" + name + "</extra>"))
    fig.update_layout(**plotly_layout(height, barmode="group", bargap=0.35, bargroupgap=0.08, hovermode="closest"))
    fig.update_yaxes(title_text="Concentration (µg/m³)", rangemode="tozero")
    show(fig, key)


def efficiency_trend(df, now, label, s, key, height=280) -> None:
    t = tok()
    span, _ = RANGES[label]
    d = df[df["timestamp"] >= pd.Timestamp(now) - span].copy()
    d["eff25"] = efficiency_series(d["inlet_pm25"], d["outlet_pm25"], s.min_inlet_for_efficiency)
    d["eff10"] = efficiency_series(d["inlet_pm10"], d["outlet_pm10"], s.min_inlet_for_efficiency)
    rule = {"1 h": "1min", "6 h": "5min", "24 h": "15min", "7 d": "1h"}[label]
    agg = d.set_index("timestamp")[["eff25", "eff10"]].resample(rule).mean().reset_index()
    fig = go.Figure()
    _line(fig, agg["timestamp"], agg["eff25"], "PM2.5 removal", t["pm25"], "%")
    _line(fig, agg["timestamp"], agg["eff10"], "PM10 removal", t["pm10"], "%")
    fig.update_layout(**plotly_layout(height))
    fig.update_yaxes(title_text="Single-pass removal efficiency (%)", range=[80, 100])
    show(fig, key)


def fan_trend(df, now, label, key, height=240) -> None:
    t = tok()
    d = window(df, now, label)
    fig = go.Figure()
    _line(fig, d["timestamp"], d["fan_command_pct"], "Command", t["accent"], "%")
    _line(fig, d["timestamp"], d["fan_feedback_pct"], "Feedback", t["series3"], "%", dash="dot", width=1.6)
    fig.update_layout(**plotly_layout(height))
    fig.update_yaxes(title_text="Fan (%)", range=[0, 105])
    show(fig, key)


def power_trend(df, now, label, key, height=280) -> None:
    t = tok()
    d = window(df, now, label)
    fig = go.Figure(go.Scatter(x=d["timestamp"], y=d["power_w"], mode="lines", name="Power",
                               line=dict(color=t["accent"], width=2), fill="tozeroy",
                               fillcolor="rgba(14,143,176,0.10)", hovertemplate="%{y:.0f} W<extra></extra>"))
    fig.update_layout(**plotly_layout(height, showlegend=False))
    fig.update_yaxes(title_text="Power (W)", rangemode="tozero")
    show(fig, key)


def daily_energy(df, key, height=280) -> None:
    t = tok()
    rows = []
    for day, g in df.groupby(df["timestamp"].dt.normalize()):
        r = energy_kwh(g["timestamp"], g["power_w"])
        rows.append((day, r.value, len(g) / 1440))
    e = pd.DataFrame(rows, columns=["day", "kwh", "coverage"])
    labels = [f"{d:%a %d %b}" + (" (partial)" if c < 0.98 else "") for d, c in zip(e["day"], e["coverage"])]
    fig = go.Figure(go.Bar(x=labels, y=e["kwh"], marker=dict(color=t["pm25"], cornerradius=4),
                           text=[f"{v:.2f}" if v is not None else "n/a" for v in e["kwh"]], textposition="outside",
                           textfont=dict(color=t["text2"]), hovertemplate="%{y:.2f} kWh<extra></extra>"))
    fig.update_layout(**plotly_layout(height, showlegend=False, hovermode="closest"))
    fig.update_yaxes(title_text="Energy (kWh per day)", rangemode="tozero")
    show(fig, key)


def dp_trend(df, now, label, s, key, height=280) -> None:
    t = tok()
    d = window(df, now, label).copy()
    d["dp_norm"] = [normalised_dp(dp, af, s.rated_airflow_m3h) for dp, af in zip(d["filter_dp_pa"], d["airflow_m3h"])]
    fig = go.Figure()
    _line(fig, d["timestamp"], d["filter_dp_pa"], "Measured ΔP", t["series3"], "Pa", dash="dot", width=1.5)
    _line(fig, d["timestamp"], d["dp_norm"], "ΔP at rated airflow (normalised)", t["accent"], "Pa")
    _ref_line(fig, s.dp_warning_pa, f"Inspect {s.dp_warning_pa:.0f} Pa (configurable)")
    _ref_line(fig, s.dp_replace_pa, f"Replace {s.dp_replace_pa:.0f} Pa (configurable)")
    fig.update_layout(**plotly_layout(height))
    fig.update_yaxes(title_text="Filter differential pressure (Pa)", rangemode="tozero")
    show(fig, key)


def airflow_trend(df, now, label, key, height=240) -> None:
    t = tok()
    d = window(df, now, label)
    fig = go.Figure()
    _line(fig, d["timestamp"], d["airflow_m3h"], "Airflow", t["outlet"], "m³/h")
    fig.update_layout(**plotly_layout(height, showlegend=False))
    fig.update_yaxes(title_text="Airflow (m³/h)", rangemode="tozero")
    show(fig, key)
