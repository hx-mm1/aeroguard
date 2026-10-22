"""Per-rerun orchestration: read sensors → step controller → evaluate alerts.

Kept free of Streamlit imports; ``state`` is any mutable mapping (in the app
it is ``st.session_state``), so the loop can be unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from services import calculations as calc
from services.config import Settings
from services.control import ControllerState, set_mode, step
from services.events import DB_PATH, EventStore, evaluate_rules, seed_demo_history
from services.sensors import (ComponentHealth, DemoSensorAdapter, SensorAdapter, SensorReading,
                              supports_demo_controls)


@dataclass
class Snapshot:
    now: pd.Timestamp
    settings: Settings
    adapter: SensorAdapter
    store: EventStore
    controller: ControllerState
    reading: SensorReading
    history: pd.DataFrame
    health: list[ComponentHealth]
    stale: bool
    aqi: calc.AQIResult
    eff_pm25: calc.Result
    eff_pm10: calc.Result
    cadr_pm25: calc.Result
    dp_normalised: Optional[float]
    energy_today: calc.Result
    clean_air_today: calc.Result
    operating_hours: Optional[float]
    filter_hours: Optional[float]
    pollution_episodes_7d: int
    open_alerts: pd.DataFrame
    command_status: str

    @property
    def simulated(self) -> bool:
        return self.adapter.is_simulated


def init_state(state) -> None:
    if "settings" not in state:
        state["settings"] = Settings.load()
    if "adapter" not in state:
        state["adapter"] = DemoSensorAdapter(state["settings"])
    if "store" not in state:
        adapter = state["adapter"]
        # Demo history is generated per session, so its log is per session too
        # (in memory). Real hardware logs to data/aeroguard.db.
        state["store"] = EventStore(None if adapter.is_simulated else DB_PATH)
        if state["store"].is_empty() and supports_demo_controls(adapter):
            seed_demo_history(state["store"], adapter.episodes, adapter.start, pd.Timestamp.now())
    if "controller" not in state:
        adapter = state["adapter"]
        hc = getattr(adapter, "history_controller", None)
        state["controller"] = ControllerState(
            mode="AUTO", command_pct=hc.command_pct if hc else 30.0,
            target_pct=hc.target_pct if hc else 30.0,
            smoothed_pm25=hc.smoothed_pm25 if hc else None, band=hc.band if hc else "CLEAN")
        state["last_tick"] = None


def change_mode(state, mode: str, now) -> bool:
    ctrl: ControllerState = state["controller"]
    old = ctrl.mode
    if set_mode(ctrl, mode):
        adapter: SensorAdapter = state["adapter"]
        if supports_demo_controls(adapter):
            adapter.mode = mode
        state["store"].log(now, "Info", "Operator", f"Mode changed {old} → {mode}",
                           simulated=adapter.is_simulated)
        return True
    return False


def tick(state, now: Optional[pd.Timestamp] = None) -> Snapshot:
    now = pd.Timestamp(now) if now is not None else pd.Timestamp.now()
    s: Settings = state["settings"]
    adapter: SensorAdapter = state["adapter"]
    store: EventStore = state["store"]
    ctrl: ControllerState = state["controller"]

    reading = adapter.latest(now)
    stale = calc.is_stale(reading.timestamp, now, s.stale_after_s)

    last = state.get("last_tick")
    dt = 0.0 if last is None else min(max((now - last).total_seconds(), 0.0), 60.0)
    state["last_tick"] = now
    step(ctrl, None if stale else reading.inlet_pm25, dt, s, simulated=adapter.is_simulated)
    command_status = adapter.send_fan_command(ctrl.command_pct)

    history = adapter.history()
    health = adapter.health(now, s)
    ramping = abs(ctrl.target_pct - ctrl.command_pct) > 0.5
    for r in evaluate_rules(reading, history, now, s, health, ramping):
        store.sync_alert(r.key, r.active, now, r.severity, r.source, r.message, adapter.is_simulated)

    use = None if stale else reading
    eff25 = calc.removal_efficiency(use and use.inlet_pm25, use and use.outlet_pm25, s.min_inlet_for_efficiency)
    eff10 = calc.removal_efficiency(use and use.inlet_pm10, use and use.outlet_pm10, s.min_inlet_for_efficiency)
    cadr25 = calc.cadr(use and use.airflow_m3h, eff25.value)
    dp_n = None if stale else calc.normalised_dp(reading.filter_dp_pa, reading.airflow_m3h, s.rated_airflow_m3h)

    today = history[history["timestamp"] >= now.normalize()] if history is not None else None
    if today is not None and len(today) >= 2:
        energy_today = calc.energy_kwh(today["timestamp"], today["power_w"])
        clean_today = calc.clean_air_m3(today, s.min_inlet_for_efficiency)
    else:
        energy_today = calc.Result(None, "Not enough data today")
        clean_today = calc.Result(None, "Not enough data today")

    week = history[history["timestamp"] >= now - pd.Timedelta(days=7)] if history is not None else None
    episodes = calc.count_exceedance_episodes(week, "inlet_pm25", s.pm25_reference)

    return Snapshot(
        now=now, settings=s, adapter=adapter, store=store, controller=ctrl, reading=reading,
        history=history, health=health, stale=stale,
        aqi=calc.aqi_from_history(history, now) if not stale else calc.AQIResult(None, None, None, None, None, "Data stale"),
        eff_pm25=eff25, eff_pm10=eff10, cadr_pm25=cadr25, dp_normalised=dp_n,
        energy_today=energy_today, clean_air_today=clean_today,
        operating_hours=adapter.operating_hours(now), filter_hours=adapter.filter_hours(now),
        pollution_episodes_7d=episodes, open_alerts=store.open_alerts(),
        command_status=command_status,
    )
