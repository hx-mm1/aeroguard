"""Event log, alerts and maintenance records (SQLite).

Alerts are state-change based: a rule raises one alert when its condition
becomes true, clears it when the condition ends, and will not raise again for
the same rule until ``COOLDOWN_S`` has passed. This keeps the log free of
duplicates when Streamlit reruns every few seconds.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from services.calculations import is_stale, is_valid_number, normalised_dp
from services.config import Settings
from services.sensors import OFFLINE, ComponentHealth, SensorReading

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "aeroguard.db"
COOLDOWN_S = 120
SEVERITIES = ("Info", "Warning", "Critical")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    severity TEXT NOT NULL,
    source TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL,          -- Active | Acknowledged | Cleared | Logged
    kind TEXT NOT NULL,            -- alert | event
    rule_key TEXT,
    simulated INTEGER NOT NULL DEFAULT 1,
    ack_ts TEXT,
    cleared_ts TEXT
);
CREATE TABLE IF NOT EXISTS maintenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT,
    performed_by TEXT,
    simulated INTEGER NOT NULL DEFAULT 1
);
"""


def _ts(t) -> str:
    return pd.Timestamp(t).strftime("%Y-%m-%d %H:%M:%S")


class EventStore:
    """SQLite-backed log. ``path=None`` keeps it in memory for this session only,
    which is what demo mode uses so that every viewer gets an independent demo."""

    def __init__(self, path: Optional[Path] = DB_PATH):
        self.path = Path(path) if path is not None else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.path) if self.path else ":memory:",
                                   timeout=5, check_same_thread=False)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(_SCHEMA)
            c.commit()

    @contextmanager
    def _conn(self):
        # one connection per store; the lock serialises Streamlit's script threads
        with self._lock:
            yield self._db

    # -- writes ---------------------------------------------------------------
    def log(self, ts, severity: str, source: str, message: str, *, kind: str = "event",
            status: str = "Logged", rule_key: Optional[str] = None, simulated: bool = True,
            cleared_ts=None) -> int:
        assert severity in SEVERITIES
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO events (ts, severity, source, message, status, kind, rule_key, simulated, cleared_ts)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (_ts(ts), severity, source, message, status, kind, rule_key, int(simulated),
                 _ts(cleared_ts) if cleared_ts is not None else None))
            c.commit()
            return cur.lastrowid

    def acknowledge(self, event_id: int, now) -> None:
        with self._conn() as c:
            c.execute("UPDATE events SET status='Acknowledged', ack_ts=? WHERE id=? AND status='Active'",
                      (_ts(now), int(event_id)))
            c.commit()

    def acknowledge_all(self, now) -> None:
        with self._conn() as c:
            c.execute("UPDATE events SET status='Acknowledged', ack_ts=? WHERE status='Active'", (_ts(now),))
            c.commit()

    def _clear(self, rule_key: str, now) -> None:
        with self._conn() as c:
            c.execute("UPDATE events SET cleared_ts=?, status=CASE WHEN status='Active' THEN 'Cleared' ELSE status END"
                      " WHERE rule_key=? AND cleared_ts IS NULL AND kind='alert'", (_ts(now), rule_key))
            c.commit()

    def add_maintenance(self, ts, action: str, detail: str, by: str, simulated: bool) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO maintenance (ts, action, detail, performed_by, simulated) VALUES (?,?,?,?,?)",
                      (_ts(ts), action, detail, by, int(simulated)))
            c.commit()

    def reset(self) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM events")
            c.execute("DELETE FROM maintenance")
            c.commit()

    # -- reads ------------------------------------------------------------------
    def events(self, limit: int = 500) -> pd.DataFrame:
        with self._conn() as c:
            return pd.read_sql_query("SELECT * FROM events ORDER BY ts DESC, id DESC LIMIT ?", c, params=(limit,))

    def open_alerts(self) -> pd.DataFrame:
        """Alerts whose condition is still present (Active or Acknowledged)."""
        with self._conn() as c:
            return pd.read_sql_query(
                "SELECT * FROM events WHERE kind='alert' AND cleared_ts IS NULL ORDER BY ts DESC", c)

    def maintenance(self) -> pd.DataFrame:
        with self._conn() as c:
            return pd.read_sql_query("SELECT * FROM maintenance ORDER BY ts DESC", c)

    def is_empty(self) -> bool:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0

    def _open_rule(self, rule_key: str) -> Optional[tuple]:
        with self._conn() as c:
            return c.execute("SELECT id, severity FROM events WHERE rule_key=? AND kind='alert' AND cleared_ts IS NULL"
                             " ORDER BY id DESC LIMIT 1", (rule_key,)).fetchone()

    def _last_cleared(self, rule_key: str) -> Optional[pd.Timestamp]:
        with self._conn() as c:
            row = c.execute("SELECT MAX(cleared_ts) FROM events WHERE rule_key=? AND kind='alert'",
                            (rule_key,)).fetchone()
        return pd.Timestamp(row[0]) if row and row[0] else None

    # -- alert engine -------------------------------------------------------------
    def sync_alert(self, rule_key: str, active: bool, now, severity: str, source: str,
                   message: str, simulated: bool) -> None:
        open_row = self._open_rule(rule_key)
        if active and open_row is None:
            last = self._last_cleared(rule_key)
            if last is not None and (pd.Timestamp(now) - last).total_seconds() < COOLDOWN_S:
                return
            self.log(now, severity, source, message, kind="alert", status="Active",
                     rule_key=rule_key, simulated=simulated)
        elif not active and open_row is not None:
            self._clear(rule_key, now)


@dataclass
class RuleResult:
    key: str
    active: bool
    severity: str
    source: str
    message: str


def evaluate_rules(reading: SensorReading, history: pd.DataFrame, now, s: Settings,
                   health: list[ComponentHealth], ramping: bool) -> list[RuleResult]:
    """Evaluate every alert rule against the latest data."""
    tag = ""
    stale = is_stale(reading.timestamp, now, s.stale_after_s)
    pm25 = reading.inlet_pm25 if not stale else None
    rules: list[RuleResult] = []

    rules.append(RuleResult(
        "stale_data", stale, "Critical", "Data link",
        f"No new sensor data for more than {s.stale_after_s} s{tag}"))

    crit = is_valid_number(pm25) and pm25 >= s.pm25_critical
    rules.append(RuleResult(
        "pm25_critical", crit, "Critical", "PM sensor — inlet",
        f"PM2.5 {pm25 if pm25 is not None else 0:.0f} µg/m³ at or above critical band "
        f"{s.pm25_critical:.0f} µg/m³{tag}"))
    rules.append(RuleResult(
        "pm25_reference", is_valid_number(pm25) and pm25 >= s.pm25_reference and not crit,
        "Warning", "PM sensor — inlet",
        f"PM2.5 {pm25 if pm25 is not None else 0:.0f} µg/m³ above configured reference "
        f"{s.pm25_reference:.0f} µg/m³{tag}"))

    rising = False
    if is_valid_number(pm25) and history is not None and not history.empty:
        window = history[history["timestamp"] >= pd.Timestamp(now) - pd.Timedelta(minutes=s.rapid_rise_window_min)]
        if not window.empty and window["inlet_pm25"].notna().any():
            rising = pm25 - window["inlet_pm25"].min() >= s.rapid_rise_ugm3
    rules.append(RuleResult(
        "pm25_rising", rising, "Warning", "PM sensor — inlet",
        f"PM2.5 rose by ≥ {s.rapid_rise_ugm3:.0f} µg/m³ within {s.rapid_rise_window_min} min{tag}"))

    dp_n = None if stale else normalised_dp(reading.filter_dp_pa, reading.airflow_m3h, s.rated_airflow_m3h)
    rules.append(RuleResult(
        "dp_replace", dp_n is not None and dp_n >= s.dp_replace_pa, "Critical", "Filter ΔP",
        f"Filter ΔP at rated airflow ≥ {s.dp_replace_pa:.0f} Pa — replace filter{tag}"))
    rules.append(RuleResult(
        "dp_warning", dp_n is not None and s.dp_warning_pa <= dp_n < s.dp_replace_pa, "Warning", "Filter ΔP",
        f"Filter ΔP at rated airflow ≥ {s.dp_warning_pa:.0f} Pa — schedule inspection{tag}"))

    outlet_missing = (not stale and is_valid_number(reading.inlet_pm25)
                      and not is_valid_number(reading.outlet_pm25))
    rules.append(RuleResult(
        "outlet_offline", outlet_missing, "Warning", "PM sensor — outlet",
        f"Outlet PM sensor not reporting — removal efficiency unavailable{tag}"))

    mismatch = False
    if not stale and not ramping and is_valid_number(reading.fan_feedback_pct) and is_valid_number(reading.fan_command_pct):
        mismatch = abs(reading.fan_feedback_pct - reading.fan_command_pct) > 15
    rules.append(RuleResult(
        "fan_mismatch", mismatch, "Warning", "Fan",
        f"Fan feedback differs from command by more than 15 %{tag}"))

    cam = next((h for h in health if h.name == "Camera"), None)
    rules.append(RuleResult(
        "camera_offline", cam is not None and cam.state == OFFLINE and not stale, "Warning", "Camera",
        f"Camera disconnected{tag}"))

    power_abn = False
    if not stale and is_valid_number(reading.power_w) and is_valid_number(reading.fan_feedback_pct):
        expected = 38 + 1050 * (reading.fan_feedback_pct / 100) ** 3  # baseline from commissioning model
        power_abn = abs(reading.power_w - expected) > max(40.0, 0.3 * expected)
    rules.append(RuleResult(
        "power_abnormal", power_abn, "Warning", "Power",
        f"Power draw outside expected range for current fan speed{tag}"))
    return rules


def seed_demo_history(store: EventStore, episodes, start, now) -> None:
    """Pre-fill the log with clearly labelled simulated history."""
    for ep in episodes:
        store.log(ep.start + pd.Timedelta(minutes=20), "Warning", "PM sensor — inlet",
                  f"PM2.5 above configured reference — {ep.label}",
                  kind="alert", status="Acknowledged", rule_key="history",
                  cleared_ts=ep.end + pd.Timedelta(minutes=40))
        store.log(ep.start + pd.Timedelta(minutes=22), "Info", "Controller",
                  "AUTO raised fan command in response to elevated PM2.5")
    store.log(start + pd.Timedelta(hours=30), "Info", "Network / data link",
              "Data link restored after 4 min interruption")
    store.log(now - pd.Timedelta(minutes=1), "Info", "System",
              "Dashboard started (demo mode)")
    now = pd.Timestamp(now)
    for days, action, detail, by in [
        (31, "Main filter replaced", "HEPA-grade main filter installed; ΔP at rated airflow 168 Pa after fitting", "Facilities technician"),
        (31, "Pre-filter replaced", "Coarse pre-filter replaced with main filter", "Facilities technician"),
        (14, "Pre-filter cleaned", "Visual inspection; light dust loading", "Facilities technician"),
        (20, "PM sensor co-location check", "Inlet/outlet sensors compared side by side for 1 h; agreement within ±1.5 µg/m³", "Engineering"),
        (45, "Camera firmware update", "Firmware updated; video recording disabled by policy", "IT"),
    ]:
        store.add_maintenance(now - pd.Timedelta(days=days), action, detail, by, True)
