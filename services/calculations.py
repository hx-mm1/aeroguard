"""Engineering calculations with defensive input handling.

Every function returns ``None`` (or a ``Result`` with ``value=None``) when the
inputs cannot support a meaningful answer, so the UI can show "Not available"
instead of inventing a number. Nothing here clamps an invalid result into a
plausible-looking range.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Result:
    value: Optional[float]
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.value is not None


def is_valid_number(x) -> bool:
    """True for a finite real number (rejects None, NaN, inf, strings, bools)."""
    if x is None or isinstance(x, bool):
        return False
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Particle removal efficiency
# ---------------------------------------------------------------------------

def removal_efficiency(inlet, outlet, min_inlet: float = 0.0) -> Result:
    """Single-pass removal efficiency in percent.

    ``((inlet - outlet) / inlet) * 100``. Requires paired, valid, non-negative
    readings and an inlet above ``min_inlet``. A negative efficiency (outlet
    higher than inlet) is returned as-is with a warning; it is not clamped.
    """
    if not is_valid_number(inlet) or not is_valid_number(outlet):
        return Result(None, "Missing or invalid inlet/outlet reading")
    inlet, outlet = float(inlet), float(outlet)
    if inlet < 0 or outlet < 0:
        return Result(None, "Negative concentration reported — check sensor")
    if inlet == 0:
        return Result(None, "Inlet concentration is zero — efficiency undefined")
    if inlet < min_inlet:
        return Result(None, f"Inlet below {min_inlet:g} µg/m³ — too low for a meaningful efficiency")
    eff = (inlet - outlet) / inlet * 100.0
    if eff < 0:
        return Result(round(eff, 1), "Outlet exceeds inlet — check sensors or bypass leakage")
    return Result(round(eff, 1))


# ---------------------------------------------------------------------------
# Clean Air Delivery Rate
# ---------------------------------------------------------------------------

def cadr(airflow_m3h, efficiency_pct) -> Result:
    """Simplified single-pollutant CADR (m³/h) = airflow × fractional efficiency."""
    if not is_valid_number(airflow_m3h):
        return Result(None, "Airflow not available")
    if not is_valid_number(efficiency_pct):
        return Result(None, "Removal efficiency not available")
    airflow, eff = float(airflow_m3h), float(efficiency_pct)
    if airflow <= 0:
        return Result(None, "Airflow is zero or negative")
    if not (0 < eff <= 100):
        return Result(None, "Efficiency outside 0–100 % — CADR not calculated")
    return Result(round(airflow * eff / 100.0, -1))  # nearest 10 m³/h: avoids false precision


# ---------------------------------------------------------------------------
# Energy
# ---------------------------------------------------------------------------

def energy_kwh(timestamps: Sequence, power_w: Sequence, max_gap_s: float = 300.0) -> Result:
    """Integrate power over time with the trapezoidal rule.

    Intervals longer than ``max_gap_s`` or touching a missing sample are not
    integrated (we do not guess what happened during a data gap).
    """
    if len(timestamps) != len(power_w):
        return Result(None, "Timestamp and power series differ in length")
    if len(timestamps) < 2:
        return Result(None, "Not enough power samples")
    t = pd.to_datetime(pd.Series(timestamps)).astype("int64").to_numpy() / 1e9
    p = pd.to_numeric(pd.Series(power_w), errors="coerce").to_numpy(dtype=float)
    dt = np.diff(t)
    p_avg = (p[:-1] + p[1:]) / 2
    usable = (dt > 0) & (dt <= max_gap_s) & np.isfinite(p_avg) & (p_avg >= 0)
    if not usable.any():
        return Result(None, "No usable power intervals")
    wh = float(np.sum(p_avg[usable] * dt[usable]) / 3600.0)
    coverage = float(dt[usable].sum() / max(dt.sum(), 1e-9))
    msg = "" if coverage > 0.95 else f"Only {coverage:.0%} of the period has power data"
    return Result(wh / 1000.0, msg)


def specific_energy_wh_per_1000m3(energy_kwh_value, clean_air_m3) -> Result:
    """Energy relative to clean air delivered (Wh per 1,000 m³)."""
    if not is_valid_number(energy_kwh_value) or not is_valid_number(clean_air_m3):
        return Result(None, "Energy or clean-air volume not available")
    if clean_air_m3 <= 0:
        return Result(None, "No clean air delivered in this period")
    return Result(round(energy_kwh_value * 1000.0 / (clean_air_m3 / 1000.0), 1))


# ---------------------------------------------------------------------------
# AQI — US EPA method (PM2.5 2024 breakpoints, PM10), NowCast averaging
# ---------------------------------------------------------------------------
# NOTE: This is the US EPA AQI, used here because its method is fully
# documented. Malaysia reports the Air Pollutant Index (API/IPU) with
# different breakpoints; results are therefore not comparable with the
# official Malaysian API. Only PM2.5 and PM10 are considered.

AQI_CATEGORIES = [
    (50, "Good"),
    (100, "Moderate"),
    (150, "Unhealthy for Sensitive Groups"),
    (200, "Unhealthy"),
    (300, "Very Unhealthy"),
    (500, "Hazardous"),
]

_PM25_BP = [  # (C_lo, C_hi, I_lo, I_hi) — EPA, effective May 2024
    (0.0, 9.0, 0, 50),
    (9.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 125.4, 151, 200),
    (125.5, 225.4, 201, 300),
    (225.5, 325.4, 301, 500),
]
_PM10_BP = [
    (0, 54, 0, 50),
    (55, 154, 51, 100),
    (155, 254, 101, 150),
    (255, 354, 151, 200),
    (355, 424, 201, 300),
    (425, 604, 301, 500),
]


def _aqi_from_bp(conc: float, table) -> Optional[int]:
    for c_lo, c_hi, i_lo, i_hi in table:
        if c_lo <= conc <= c_hi:
            return round((i_hi - i_lo) / (c_hi - c_lo) * (conc - c_lo) + i_lo)
    return None


def aqi_pm25(conc) -> Optional[int]:
    if not is_valid_number(conc) or conc < 0:
        return None
    c = math.floor(float(conc) * 10) / 10  # EPA: truncate to 0.1 µg/m³
    return _aqi_from_bp(c, _PM25_BP) if c <= 325.4 else 500


def aqi_pm10(conc) -> Optional[int]:
    if not is_valid_number(conc) or conc < 0:
        return None
    c = math.floor(float(conc))  # EPA: truncate to 1 µg/m³
    return _aqi_from_bp(c, _PM10_BP) if c <= 604 else 500


def aqi_category(aqi) -> Optional[str]:
    if aqi is None:
        return None
    for upper, name in AQI_CATEGORIES:
        if aqi <= upper:
            return name
    return "Hazardous"


def nowcast(hourly_avgs_recent_first: Sequence) -> Optional[float]:
    """EPA NowCast for PM from up to 12 hourly averages (most recent first).

    Requires at least two of the three most recent hours to be valid.
    """
    vals = [float(v) if is_valid_number(v) and v >= 0 else None
            for v in list(hourly_avgs_recent_first)[:12]]
    if sum(v is not None for v in vals[:3]) < 2:
        return None
    present = [v for v in vals if v is not None]
    c_max, c_min = max(present), min(present)
    w = 1.0 if c_max == 0 else c_min / c_max
    w = max(w, 0.5)
    num = den = 0.0
    for i, v in enumerate(vals):
        if v is None:
            continue
        num += (w ** i) * v
        den += w ** i
    return num / den if den else None


@dataclass(frozen=True)
class AQIResult:
    value: Optional[int]
    category: Optional[str]
    dominant: Optional[str]
    pm25_nowcast: Optional[float]
    pm10_nowcast: Optional[float]
    message: str = ""


def aqi_from_history(df: pd.DataFrame, now: pd.Timestamp,
                     pm25_col: str = "inlet_pm25", pm10_col: str = "inlet_pm10") -> AQIResult:
    """Compute the PM-only US EPA AQI (NowCast) from a minute-level history."""
    if df is None or df.empty:
        return AQIResult(None, None, None, None, None, "No history")
    window = df[(df["timestamp"] > now - pd.Timedelta(hours=12)) & (df["timestamp"] <= now)]
    if window.empty:
        return AQIResult(None, None, None, None, None, "No data in the last 12 h")
    hours_ago = ((now - window["timestamp"]) // pd.Timedelta(hours=1)).astype(int)
    out = {}
    for col in (pm25_col, pm10_col):
        grouped = window.groupby(hours_ago)[col].agg(["mean", "count"])
        # an hour counts only when at least 75 % of its minutes are present
        hourly = [grouped.loc[h, "mean"] if h in grouped.index and grouped.loc[h, "count"] >= 45 else None
                  for h in range(12)]
        # the current partial hour is accepted if it has ≥ 10 minutes
        if 0 in grouped.index and hourly[0] is None and grouped.loc[0, "count"] >= 10:
            hourly[0] = grouped.loc[0, "mean"]
        out[col] = nowcast(hourly)
    a25, a10 = aqi_pm25(out[pm25_col]), aqi_pm10(out[pm10_col])
    candidates = [(a, n) for a, n in ((a25, "PM2.5"), (a10, "PM10")) if a is not None]
    if not candidates:
        return AQIResult(None, None, None, out[pm25_col], out[pm10_col], "Insufficient recent data")
    value, dominant = max(candidates)
    return AQIResult(value, aqi_category(value), dominant, out[pm25_col], out[pm10_col])


def efficiency_series(inlet: pd.Series, outlet: pd.Series, min_inlet: float = 0.0) -> pd.Series:
    """Vectorised removal efficiency (%). Invalid pairs become NaN, not 0."""
    i = pd.to_numeric(inlet, errors="coerce")
    o = pd.to_numeric(outlet, errors="coerce")
    valid = i.notna() & o.notna() & (i > 0) & (i >= min_inlet) & (o >= 0)
    return ((i - o) / i * 100).where(valid)


def clean_air_m3(df: pd.DataFrame, min_inlet: float = 0.0, max_gap_s: float = 300.0) -> Result:
    """Integrate PM2.5 CADR over time → equivalent volume of particle-free air (m³)."""
    if df is None or len(df) < 2:
        return Result(None, "Not enough data")
    eff = efficiency_series(df["inlet_pm25"], df["outlet_pm25"], min_inlet)
    rate = pd.to_numeric(df["airflow_m3h"], errors="coerce") * eff / 100  # m³/h
    rate = rate.where((eff > 0) & (eff <= 100))
    t = pd.to_datetime(df["timestamp"]).astype("int64").to_numpy() / 1e9
    dt = np.diff(t)
    r = rate.to_numpy(dtype=float)
    mid = (r[:-1] + r[1:]) / 2
    usable = (dt > 0) & (dt <= max_gap_s) & np.isfinite(mid)
    if not usable.any():
        return Result(None, "No valid paired readings with airflow")
    return Result(float(np.sum(mid[usable] * dt[usable]) / 3600.0))


def count_exceedance_episodes(df: pd.DataFrame, col: str, threshold: float,
                              min_duration_min: int = 5, merge_gap_min: int = 10) -> int:
    """Count separate periods where ``col`` stays at/above ``threshold``.

    Runs separated by less than ``merge_gap_min`` are merged; runs shorter than
    ``min_duration_min`` are ignored as noise.
    """
    if df is None or df.empty:
        return 0
    above = df.loc[pd.to_numeric(df[col], errors="coerce") >= threshold, "timestamp"]
    if above.empty:
        return 0
    ts = pd.to_datetime(above).sort_values().reset_index(drop=True)
    breaks = ts.diff() > pd.Timedelta(minutes=merge_gap_min)
    groups = breaks.cumsum()
    durations = ts.groupby(groups).agg(lambda s: (s.iloc[-1] - s.iloc[0]).total_seconds() / 60)
    return int((durations >= min_duration_min).sum())


# ---------------------------------------------------------------------------
# Filter loading
# ---------------------------------------------------------------------------

def normalised_dp(dp_pa, airflow_m3h, rated_airflow_m3h, exponent: float = 1.4,
                  min_fraction: float = 0.2) -> Optional[float]:
    """Filter ΔP scaled to rated airflow, so loading can be compared across fan speeds.

    ΔP across a filter rises with airflow (roughly ∝ flow^1.4 for pleated media).
    Below ``min_fraction`` of rated airflow the scaling is too uncertain, so
    ``None`` is returned.
    """
    if not all(is_valid_number(v) for v in (dp_pa, airflow_m3h, rated_airflow_m3h)):
        return None
    if dp_pa < 0 or rated_airflow_m3h <= 0:
        return None
    frac = airflow_m3h / rated_airflow_m3h
    if frac < min_fraction:
        return None
    return dp_pa / frac ** exponent


# ---------------------------------------------------------------------------
# Data freshness & formatting
# ---------------------------------------------------------------------------

def is_stale(last_ts, now, stale_after_s: float) -> bool:
    if last_ts is None or pd.isna(last_ts):
        return True
    return (pd.Timestamp(now) - pd.Timestamp(last_ts)).total_seconds() > stale_after_s


def fmt(value, decimals: int = 0, unit: str = "", na: str = "Not available") -> str:
    """Format a value with sensible precision, or 'Not available'."""
    if not is_valid_number(value):
        return na
    text = f"{float(value):,.{decimals}f}"
    return f"{text} {unit}".strip()
