"""Supervisory fan-command logic for ECO / AUTO / BOOST.

This decides a *requested* fan command. It is supervisory only: motor
protection, current limits and interlocks belong in the hardware controller,
which must enforce its own limits regardless of what this layer requests.

Stability measures:
- PM2.5 is smoothed with an exponential moving average.
- AUTO uses discrete bands with hysteresis (step up on crossing a band edge,
  step down only once the reading falls ``band_hysteresis`` below it).
- The command is rate-limited (``ramp_pct_per_s``) so it never jumps.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from services.calculations import is_valid_number
from services.config import Settings

MODES = ("ECO", "AUTO", "BOOST")
BANDS = ("CLEAN", "ELEVATED", "HIGH", "SEVERE")


@dataclass
class ControllerState:
    mode: str = "AUTO"
    command_pct: float = 30.0
    target_pct: float = 30.0
    smoothed_pm25: Optional[float] = None
    band: str = "CLEAN"
    reason: str = "Starting up"


def _band_edges(s: Settings):
    return (s.pm25_low, s.pm25_high, s.pm25_critical)


def next_band(current: str, pm25: float, s: Settings) -> str:
    """Band selection with hysteresis on the downward transitions."""
    edges = _band_edges(s)
    idx = BANDS.index(current)
    # step up as far as the reading justifies
    while idx < 3 and pm25 >= edges[idx]:
        idx += 1
    # step down only when clearly below the lower edge of the current band
    while idx > 0 and pm25 < edges[idx - 1] - s.band_hysteresis:
        idx -= 1
    return BANDS[idx]


def band_target(band: str, s: Settings) -> float:
    lo, hi = s.auto_min_pct, s.auto_max_pct
    return {
        "CLEAN": lo,
        "ELEVATED": lo + (hi - lo) * 0.35,
        "HIGH": lo + (hi - lo) * 0.70,
        "SEVERE": hi,
    }[band]


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def step(state: ControllerState, pm25, dt_s: float, s: Settings,
         simulated: bool = True) -> ControllerState:
    """Advance the controller by ``dt_s`` seconds given the latest PM2.5."""
    prefix = ""
    if is_valid_number(pm25) and pm25 >= 0:
        if state.smoothed_pm25 is None:
            state.smoothed_pm25 = float(pm25)
        else:
            # weight scales with elapsed time so that rerun frequency doesn't matter
            k = 1 - math.exp(-max(dt_s, 0.0) / max(s.smoothing_tau_s, 1.0))
            state.smoothed_pm25 += k * (float(pm25) - state.smoothed_pm25)
        state.band = next_band(state.band, state.smoothed_pm25, s)
        pm_ok = True
    else:
        pm_ok = False

    pm_txt = f"{state.smoothed_pm25:.0f} µg/m³" if state.smoothed_pm25 is not None else "n/a"
    auto_target = band_target(state.band, s)

    if state.mode == "BOOST":
        target = s.boost_pct
        reason = f"BOOST requested by operator — fan command held at {target:.0f} %"
    elif not pm_ok:
        # no valid PM reading: hold a safe, moderate command instead of guessing
        target = clamp(max(state.command_pct, s.auto_min_pct), s.hard_min_pct, s.hard_max_pct)
        reason = "PM2.5 reading unavailable — holding current fan command"
    elif state.mode == "ECO":
        target = min(auto_target, s.eco_cap_pct)
        if auto_target > s.eco_cap_pct:
            reason = (f"{prefix}PM2.5 {state.band.lower()} ({pm_txt}) — ECO cap "
                      f"{s.eco_cap_pct:.0f} % reached; switch to AUTO for more airflow")
        else:
            reason = f"{prefix}PM2.5 {state.band.lower()} ({pm_txt}) — ECO keeps fan low"
    else:  # AUTO
        target = auto_target
        reason = {
            "CLEAN": f"{prefix}PM2.5 low ({pm_txt}) — minimum AUTO airflow",
            "ELEVATED": f"Elevated {prefix.lower()}PM2.5 ({pm_txt}) — fan command increased",
            "HIGH": f"High {prefix.lower()}PM2.5 ({pm_txt}) — fan command raised",
            "SEVERE": f"Severe {prefix.lower()}PM2.5 ({pm_txt}) — AUTO at maximum",
        }[state.band]

    target = clamp(target, s.hard_min_pct, s.hard_max_pct)
    max_delta = s.ramp_pct_per_s * max(dt_s, 0.0)
    delta = clamp(target - state.command_pct, -max_delta, max_delta)
    state.command_pct = clamp(state.command_pct + delta, s.hard_min_pct, s.hard_max_pct)
    state.target_pct = target
    if abs(target - state.command_pct) > 0.5:
        reason += f" (ramping {state.command_pct:.0f} → {target:.0f} %)"
    state.reason = reason
    return state


def set_mode(state: ControllerState, mode: str) -> bool:
    """Change mode on an explicit operator action. Returns True if it changed."""
    if mode not in MODES:
        raise ValueError(f"Unknown mode {mode!r}")
    if mode == state.mode:
        return False
    state.mode = mode
    return True
