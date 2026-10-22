"""Sensor data layer.

The dashboard only talks to a ``SensorAdapter``. ``DemoSensorAdapter`` is the
built-in simulator; a real ESP32 / serial / MQTT source replaces it by
implementing the same interface (see README, "Connecting real sensors").
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from services.calculations import normalised_dp
from services.config import Settings
from services.control import ControllerState, step

HISTORY_COLUMNS = [
    "timestamp", "inlet_pm25", "inlet_pm10", "outlet_pm25", "outlet_pm10",
    "temperature_c", "humidity_pct", "fan_command_pct", "fan_feedback_pct",
    "airflow_m3h", "filter_dp_pa", "power_w", "mode",
]


@dataclass
class SensorReading:
    """One snapshot of every channel. ``None`` means not measured/unavailable."""
    timestamp: pd.Timestamp
    inlet_pm25: Optional[float] = None
    inlet_pm10: Optional[float] = None
    outlet_pm25: Optional[float] = None
    outlet_pm10: Optional[float] = None
    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    voc_index: Optional[float] = None  # not configured on the demo unit
    co2_ppm: Optional[float] = None  # not configured on the demo unit
    airflow_m3h: Optional[float] = None
    filter_dp_pa: Optional[float] = None
    power_w: Optional[float] = None
    fan_command_pct: Optional[float] = None
    fan_feedback_pct: Optional[float] = None
    simulated: bool = True


def supports_demo_controls(adapter) -> bool:
    """Duck-typed check (survives Streamlit hot-reloading the class during development)."""
    return hasattr(adapter, "start_pollution_event") and hasattr(adapter, "faults")


NORMAL, WARNING, OFFLINE, NOT_CONFIGURED ="Normal", "Warning", "Offline", "Not Configured"


@dataclass
class ComponentHealth:
    name: str
    state: str
    detail: str = ""
    simulated: bool = True


class SensorAdapter(ABC):
    """Interface every data source implements."""

    name: str = "Abstract adapter"
    is_simulated: bool = False
    description: str = ""

    @abstractmethod
    def latest(self, now: pd.Timestamp) -> SensorReading:
        """Return the most recent reading (its timestamp may be older than ``now``)."""

    @abstractmethod
    def history(self) -> pd.DataFrame:
        """Return stored readings with ``HISTORY_COLUMNS``."""

    @abstractmethod
    def health(self, now: pd.Timestamp, settings: Settings) -> list[ComponentHealth]:
        """Return the status of each subsystem."""

    def send_fan_command(self, pct: float) -> str:
        """Forward a fan command to hardware. Returns a short status string."""
        return "No fan actuator connected — command not sent"

    def channels(self) -> dict[str, bool]:
        """Which measurement channels this source provides."""
        return {}

    def operating_hours(self, now: pd.Timestamp) -> Optional[float]:
        return None

    def filter_hours(self, now: pd.Timestamp) -> Optional[float]:
        return None


# ---------------------------------------------------------------------------
# Demo simulator
# ---------------------------------------------------------------------------

def _smoothstep(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


@dataclass
class _Episode:
    start: pd.Timestamp
    end: Optional[pd.Timestamp]
    add_pm25: float
    add_pm10: float
    label: str
    ramp_s: float = 25 * 60
    decay_s: float = 45 * 60

    def contribution(self, ts: pd.Timestamp) -> tuple[float, float]:
        if ts < self.start:
            return 0.0, 0.0
        rise = _smoothstep((ts - self.start).total_seconds() / self.ramp_s)
        if self.end is not None and ts > self.end:
            rise *= math.exp(-(ts - self.end).total_seconds() / (self.decay_s / 3))
        return self.add_pm25 * rise, self.add_pm10 * rise


@dataclass
class DemoSensorAdapter(SensorAdapter):
    """Seeded, closed-loop simulator. Stable across Streamlit reruns because the
    instance lives in session state and only appends new minutes."""

    settings: Settings
    seed: int = 7
    days: int = 7
    name: str = "Demo simulator"
    is_simulated: bool = True
    description: str = ("Built-in seeded simulator. All values are generated for "
                        "demonstration and are not measurements.")
    faults: dict = field(default_factory=lambda: {
        "outlet_sensor": False, "camera": False, "data_link": False})

    def __post_init__(self):
        self.rng = np.random.default_rng(self.seed)
        now = pd.Timestamp.now().floor("min")
        self.start = now - pd.Timedelta(days=self.days)
        today = now.normalize()
        self._day_mult = {}
        self.episodes = [
            _Episode(today - pd.Timedelta(days=5) + pd.Timedelta(hours=7.5),
                     today - pd.Timedelta(days=5) + pd.Timedelta(hours=10), 46, 70,
                     "Traffic congestion episode"),
            _Episode(today - pd.Timedelta(days=3) + pd.Timedelta(hours=14),
                     today - pd.Timedelta(days=3) + pd.Timedelta(hours=16), 18, 120,
                     "Coarse dust episode (nearby works)"),
            _Episode(today - pd.Timedelta(days=1) + pd.Timedelta(hours=17.5),
                     today - pd.Timedelta(days=1) + pd.Timedelta(hours=21.5), 58, 90,
                     "Regional haze episode"),
        ]
        self.live_episode: Optional[_Episode] = None
        self._ar25 = 1.0
        self._ar10 = 1.0
        self._feedback = 30.0
        self.command_pct = 30.0
        self.mode = "AUTO"
        self.history_controller = ControllerState(mode="AUTO", command_pct=30.0, target_pct=30.0)
        self._rows: list[dict] = []
        self._df: Optional[pd.DataFrame] = None
        self._last_ts = self.start - pd.Timedelta(minutes=1)
        self._advance_to(now, closed_loop=True)
        self.command_pct = self.history_controller.command_pct
        self._last_reading: Optional[SensorReading] = None
        self.hours_base = 1286.0
        self.filter_hours_base = 742.0

    # -- simulation model ---------------------------------------------------
    def _mult(self, day: pd.Timestamp) -> float:
        if day not in self._day_mult:
            # deterministic per calendar day so reruns and restarts agree
            r = np.random.default_rng(self.seed * 100003 + day.toordinal())
            self._day_mult[day] = float(np.clip(r.lognormal(0, 0.18), 0.7, 1.45))
        return self._day_mult[day]

    @staticmethod
    def _diurnal(h: float) -> float:
        return (11.0 + 9.0 * math.exp(-((h - 8.5) ** 2) / (2 * 1.5 ** 2))
                + 7.0 * math.exp(-((h - 19.0) ** 2) / (2 * 2.0 ** 2))
                - 2.5 * math.exp(-((h - 4.0) ** 2) / 8.0))

    def _episode_add(self, ts) -> tuple[float, float]:
        a25 = a10 = 0.0
        for ep in self.episodes + ([self.live_episode] if self.live_episode else []):
            c25, c10 = ep.contribution(ts)
            a25 += c25
            a10 += c10
        return a25, a10

    def _sample(self, ts: pd.Timestamp, cmd: float, dt_s: float, advance: bool) -> dict:
        rng = self.rng
        h = ts.hour + ts.minute / 60 + ts.second / 3600
        if advance:
            self._ar25 = 1 + 0.93 * (self._ar25 - 1) + rng.normal(0, 0.035)
            self._ar10 = 1 + 0.90 * (self._ar10 - 1) + rng.normal(0, 0.045)
        a25, a10 = self._episode_add(ts)
        base25 = self._diurnal(h) * self._mult(ts.normalize()) * self._ar25
        inlet25 = max(0.5, base25 + a25 + rng.normal(0, 0.4))
        inlet10 = max(inlet25 * 1.05, base25 * 1.75 * self._ar10 + a10 + rng.normal(0, 1.0))

        self._feedback += (cmd - self._feedback) * (1 - math.exp(-dt_s / 3.0))
        fb = max(0.0, self._feedback + rng.normal(0, 0.4))
        frac = fb / 100.0
        days_in = (ts - self.start).total_seconds() / 86400
        dp_rated = 205.0 + 1.5 * days_in
        airflow = self.settings.rated_airflow_m3h * frac * (1 - 0.05 * dp_rated / 300) * (1 + rng.normal(0, 0.01))
        dp = dp_rated * frac ** 1.4 + rng.normal(0, 1.5)
        eff25 = 0.94 - 0.05 * (frac - 0.3) + rng.normal(0, 0.004)
        eff10 = 0.975 - 0.02 * (frac - 0.3) + rng.normal(0, 0.003)
        out25 = max(0.0, inlet25 * (1 - eff25) + rng.normal(0, 0.2))
        out10 = max(0.0, inlet10 * (1 - eff10) + rng.normal(0, 0.4))
        phase = math.sin(2 * math.pi * (h - 9) / 24)
        cam_w = 0.0 if self.faults["camera"] else 6.0
        power = 32.0 + cam_w + 1050.0 * frac ** 3 + rng.normal(0, 2.5)
        outlet_ok = not self.faults["outlet_sensor"]
        return {
            "timestamp": ts,
            "inlet_pm25": round(inlet25, 1),
            "inlet_pm10": round(inlet10, 1),
            "outlet_pm25": round(out25, 1) if outlet_ok else np.nan,
            "outlet_pm10": round(out10, 1) if outlet_ok else np.nan,
            "temperature_c": round(27.5 + 3.5 * phase + rng.normal(0, 0.15), 1),
            "humidity_pct": round(72.0 - 12.0 * phase + rng.normal(0, 0.8), 1),
            "fan_command_pct": round(cmd, 1),
            "fan_feedback_pct": round(fb, 1),
            "airflow_m3h": round(max(airflow, 0.0), 0),
            "filter_dp_pa": round(max(dp, 0.0), 1),
            "power_w": round(max(power, 0.0), 1),
            "mode": self.mode,
        }

    def _advance_to(self, now: pd.Timestamp, closed_loop: bool = False) -> None:
        """Append one row per elapsed whole minute up to ``now``."""
        target = now.floor("min")
        ts = self._last_ts + pd.Timedelta(minutes=1)
        added = False
        while ts <= target:
            if closed_loop:  # history generation runs its own AUTO controller
                row = self._sample(ts, self.history_controller.command_pct, 60.0, True)
                step(self.history_controller, row["inlet_pm25"], 60.0, self.settings)
            else:
                row = self._sample(ts, self.command_pct, 60.0, True)
            self._rows.append(row)
            self._last_ts = ts
            ts += pd.Timedelta(minutes=1)
            added = True
        if added or self._df is None:
            self._df = pd.DataFrame(self._rows, columns=HISTORY_COLUMNS)

    # -- SensorAdapter API ----------------------------------------------------
    def latest(self, now: pd.Timestamp) -> SensorReading:
        now = pd.Timestamp(now)
        if self.faults["data_link"]:
            # nothing arrives while the link is down; the last reading goes stale
            if self._last_reading is None:
                self._last_reading = SensorReading(timestamp=self._last_ts)
            return self._last_reading
        if now.floor("min") - self._last_ts > pd.Timedelta(minutes=5):
            # resuming after a link outage: leave a gap rather than backfilling
            self._last_ts = now.floor("min") - pd.Timedelta(minutes=1)
        self._advance_to(now)
        prev = self._last_reading.timestamp if self._last_reading is not None else now
        dt = min(max((now - prev).total_seconds(), 1.0), 60.0)
        row = self._sample(now, self.command_pct, dt, False)
        self._last_reading = SensorReading(
            timestamp=now.floor("s"),
            inlet_pm25=row["inlet_pm25"], inlet_pm10=row["inlet_pm10"],
            outlet_pm25=None if pd.isna(row["outlet_pm25"]) else row["outlet_pm25"],
            outlet_pm10=None if pd.isna(row["outlet_pm10"]) else row["outlet_pm10"],
            temperature_c=row["temperature_c"], humidity_pct=row["humidity_pct"],
            airflow_m3h=row["airflow_m3h"], filter_dp_pa=row["filter_dp_pa"],
            power_w=row["power_w"], fan_command_pct=row["fan_command_pct"],
            fan_feedback_pct=row["fan_feedback_pct"], simulated=True,
        )
        return self._last_reading

    def history(self) -> pd.DataFrame:
        return self._df

    def send_fan_command(self, pct: float) -> str:
        self.command_pct = float(pct)
        return "Simulated fan command applied to the demo model (no motor actuated)"

    def channels(self) -> dict[str, bool]:
        return {"PM2.5 / PM10 (inlet)": True, "PM2.5 / PM10 (outlet)": True,
                "Temperature / RH": True, "Airflow": True, "Filter ΔP": True,
                "Power": True, "Fan feedback": True, "VOC": False, "CO₂": False}

    def operating_hours(self, now) -> float:
        return self.hours_base + (pd.Timestamp(now) - self.start).total_seconds() / 3600

    def filter_hours(self, now) -> float:
        return self.filter_hours_base + (pd.Timestamp(now) - self.start).total_seconds() / 3600

    def health(self, now, settings: Settings) -> list[ComponentHealth]:
        r = self._last_reading
        link_down = self.faults["data_link"]
        out = []
        if link_down or r is None or r.fan_feedback_pct is None:
            out.append(ComponentHealth("Fan", OFFLINE if link_down else WARNING, "No feedback received"))
        else:
            gap = abs(r.fan_feedback_pct - (r.fan_command_pct or 0))
            state = NORMAL if gap <= 15 else WARNING
            out.append(ComponentHealth("Fan", state, f"Feedback {r.fan_feedback_pct:.0f} % vs command {r.fan_command_pct:.0f} %"))
        out.append(ComponentHealth("PM sensor — inlet", OFFLINE if link_down else NORMAL,
                                   "No data" if link_down else "Reporting every second"))
        if self.faults["outlet_sensor"]:
            out.append(ComponentHealth("PM sensor — outlet", OFFLINE, "No outlet readings"))
        else:
            out.append(ComponentHealth("PM sensor — outlet", OFFLINE if link_down else NORMAL,
                                       "No data" if link_down else "Reporting every second"))
        out.append(ComponentHealth("Temperature / RH sensor", OFFLINE if link_down else NORMAL,
                                   "No data" if link_down else "Reporting"))
        dp_norm = None
        if r is not None and r.filter_dp_pa and r.airflow_m3h:
            dp_norm = normalised_dp(r.filter_dp_pa, r.airflow_m3h, settings.rated_airflow_m3h)
        if link_down:
            out.append(ComponentHealth("Filter ΔP sensor", OFFLINE, "No data"))
        elif dp_norm is None:
            out.append(ComponentHealth("Filter ΔP sensor", NORMAL, "Airflow too low to normalise ΔP"))
        else:
            state = WARNING if dp_norm >= settings.dp_warning_pa else NORMAL
            out.append(ComponentHealth("Filter ΔP sensor", state, f"{dp_norm:.0f} Pa at rated airflow"))
        out.append(ComponentHealth("Camera", OFFLINE if (self.faults["camera"] or link_down) else NORMAL,
                                   "Disconnected" if self.faults["camera"] else
                                   ("No data" if link_down else "Heartbeat OK (no video integration)")))
        out.append(ComponentHealth("Network / data link", OFFLINE if link_down else NORMAL,
                                   "Link lost" if link_down else "Connected"))
        out.append(ComponentHealth("VOC / CO₂ sensors", NOT_CONFIGURED, "Not fitted on this unit"))
        return out

    # -- demo controls ----------------------------------------------------------
    def start_pollution_event(self, now) -> None:
        self.live_episode = _Episode(pd.Timestamp(now), None, 62.0, 105.0,
                                     "Operator-triggered demo pollution event",
                                     ramp_s=40.0, decay_s=90.0)

    def end_pollution_event(self, now) -> None:
        if self.live_episode is not None and self.live_episode.end is None:
            self.live_episode.end = pd.Timestamp(now)
            self.episodes.append(self.live_episode)
            self.live_episode = None

    @property
    def event_active(self) -> bool:
        return self.live_episode is not None
