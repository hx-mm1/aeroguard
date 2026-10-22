"""Configurable settings for the AeroGuard dashboard.

Settings are plain, non-secret values. They are kept in Streamlit session state
and can be saved to ``data/settings.json``. Never put credentials, broker
passwords or API keys in this file or in settings.json — real adapters should
read those from environment variables.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "settings.json"


@dataclass
class Settings:
    # Identity
    tower_id: str = "AG-001"
    site_name: str = "Main Lobby"

    # Air-quality reference thresholds (µg/m³). These are configurable
    # operating references for this prototype, not universal health limits.
    pm25_reference: float = 35.0
    pm10_reference: float = 100.0

    # AUTO control bands on smoothed PM2.5 (µg/m³)
    pm25_low: float = 12.0
    pm25_high: float = 35.0
    pm25_critical: float = 55.0
    band_hysteresis: float = 3.0  # µg/m³ a reading must fall below a band edge to step down
    smoothing_tau_s: float = 20.0  # EMA time constant applied to PM2.5 before banding
    rapid_rise_ugm3: float = 15.0  # alert if PM2.5 rises this much...
    rapid_rise_window_min: int = 10  # ...within this many minutes

    # Fan command limits (%). Hardware must enforce its own independent limits.
    hard_min_pct: float = 15.0
    hard_max_pct: float = 100.0
    eco_cap_pct: float = 45.0
    auto_min_pct: float = 25.0
    auto_max_pct: float = 90.0
    boost_pct: float = 95.0
    ramp_pct_per_s: float = 2.0  # max change in fan command per second

    # Filter & sensors
    dp_warning_pa: float = 250.0
    dp_replace_pa: float = 320.0
    stale_after_s: int = 120
    min_inlet_for_efficiency: float = 2.0  # µg/m³; below this, efficiency is not meaningful
    rated_airflow_m3h: float = 6000.0  # simulated airflow at 100 % fan command

    # Rough filter-life estimate (clearly marked as an estimate in the UI)
    filter_rated_hours: float = 4000.0

    @classmethod
    def load(cls) -> "Settings":
        if SETTINGS_PATH.exists():
            try:
                raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                known = {f.name for f in fields(cls)}
                return cls(**{k: v for k, v in raw.items() if k in known})
            except (OSError, ValueError, TypeError):
                pass
        return cls()

    def save(self) -> None:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    def validate(self) -> list[str]:
        """Return a list of human-readable problems (empty when valid)."""
        problems = []
        if not (0 <= self.hard_min_pct < self.hard_max_pct <= 100):
            problems.append("Fan hard limits must satisfy 0 ≤ min < max ≤ 100.")
        if not (self.hard_min_pct <= self.auto_min_pct < self.auto_max_pct <= self.hard_max_pct):
            problems.append("AUTO range must sit inside the hard limits, with min < max.")
        if not (self.hard_min_pct <= self.eco_cap_pct <= self.hard_max_pct):
            problems.append("ECO cap must sit inside the hard limits.")
        if not (self.hard_min_pct <= self.boost_pct <= self.hard_max_pct):
            problems.append("BOOST level must sit inside the hard limits.")
        if not (0 < self.pm25_low < self.pm25_high < self.pm25_critical):
            problems.append("PM2.5 bands must satisfy 0 < low < high < critical.")
        if self.band_hysteresis < 0 or self.band_hysteresis >= self.pm25_low:
            problems.append("Hysteresis must be ≥ 0 and smaller than the low band.")
        if not (1 <= self.smoothing_tau_s <= 600):
            problems.append("Smoothing time constant must be between 1 and 600 s.")
        if self.ramp_pct_per_s <= 0:
            problems.append("Ramp rate must be positive.")
        if not (0 < self.dp_warning_pa < self.dp_replace_pa):
            problems.append("Filter ΔP warning must be below the replace level.")
        return problems
