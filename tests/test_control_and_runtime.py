import pandas as pd
import pytest

from services.config import Settings
from services.control import ControllerState, next_band, set_mode, step
from services.events import EventStore
from services.runtime import change_mode, init_state, tick


# --- control ------------------------------------------------------------------------

def test_band_hysteresis_prevents_chatter():
    s = Settings()  # low 12, high 35, critical 55, hysteresis 3
    assert next_band("CLEAN", 12.5, s) == "ELEVATED"
    assert next_band("ELEVATED", 11.0, s) == "ELEVATED"  # within hysteresis: stay
    assert next_band("ELEVATED", 8.9, s) == "CLEAN"
    assert next_band("CLEAN", 60, s) == "SEVERE"


def test_ramp_rate_limits_command():
    s = Settings()
    c = ControllerState(mode="BOOST", command_pct=30)
    step(c, 10, 5, s)
    assert c.command_pct == pytest.approx(30 + s.ramp_pct_per_s * 5)
    for _ in range(100):
        step(c, 10, 5, s)
    assert c.command_pct == pytest.approx(s.boost_pct)


def test_eco_is_capped_and_explains():
    s = Settings()
    c = ControllerState(mode="ECO", command_pct=s.eco_cap_pct)
    for _ in range(50):
        step(c, 80, 10, s)
    assert c.command_pct <= s.eco_cap_pct
    assert "ECO cap" in c.reason


def test_auto_rises_with_pm_and_stays_in_limits():
    s = Settings()
    c = ControllerState(mode="AUTO", command_pct=s.auto_min_pct)
    for _ in range(60):
        step(c, 70, 5, s)
    assert c.band == "SEVERE"
    assert c.command_pct == pytest.approx(s.auto_max_pct)
    assert s.hard_min_pct <= c.command_pct <= s.hard_max_pct


def test_missing_pm_holds_command():
    s = Settings()
    c = ControllerState(mode="AUTO", command_pct=50)
    step(c, None, 5, s)
    assert c.command_pct == 50
    assert "unavailable" in c.reason


def test_set_mode_requires_valid_mode():
    c = ControllerState()
    assert set_mode(c, "BOOST") is True
    assert set_mode(c, "BOOST") is False
    with pytest.raises(ValueError):
        set_mode(c, "TURBO")


def test_settings_validation():
    assert Settings().validate() == []
    bad = Settings(auto_min_pct=95, auto_max_pct=90, pm25_low=40)
    assert len(bad.validate()) >= 2


# --- end-to-end demo loop -------------------------------------------------------------

@pytest.fixture
def state():
    st = {"settings": Settings()}
    init_state(st)
    return st


def test_demo_sessions_are_independent():
    a, b = {"settings": Settings()}, {"settings": Settings()}
    init_state(a)
    init_state(b)
    assert a["store"].path is None  # demo log lives in memory, never on disk
    change_mode(a, "BOOST", pd.Timestamp.now())
    assert a["store"].events()["message"].str.contains("BOOST").any()
    assert not b["store"].events()["message"].str.contains("BOOST").any()


def test_file_store_persists(tmp_path):
    path = tmp_path / "log.db"
    EventStore(path).log(pd.Timestamp.now(), "Info", "Test", "hello", simulated=False)
    assert EventStore(path).events()["message"].tolist() == ["hello"]


def test_demo_is_labelled_and_stable(state):
    snap = tick(state)
    assert snap.simulated and snap.reading.simulated
    n = len(snap.history)
    snap2 = tick(state, snap.now + pd.Timedelta(seconds=2))
    # reruns within the same minute must not regenerate or reshuffle history
    assert len(snap2.history) in (n, n + 1)
    pd.testing.assert_frame_equal(snap.history.iloc[: n - 1], snap2.history.iloc[: n - 1])


def test_pollution_event_raises_fan_and_logs(state):
    now = pd.Timestamp.now()
    tick(state, now)
    before = state["controller"].command_pct
    state["adapter"].start_pollution_event(now)
    for i in range(1, 25):
        snap = tick(state, now + pd.Timedelta(seconds=5 * i))
    assert snap.reading.inlet_pm25 > 50
    assert state["controller"].command_pct > before
    keys = set(snap.store.open_alerts()["rule_key"])
    assert "pm25_critical" in keys


def test_outlet_fault_makes_efficiency_unavailable(state):
    state["adapter"].faults["outlet_sensor"] = True
    snap = tick(state)
    assert snap.eff_pm25.value is None and snap.cadr_pm25.value is None


def test_data_link_loss_goes_stale(state):
    now = pd.Timestamp.now()
    tick(state, now)
    state["adapter"].faults["data_link"] = True
    snap = tick(state, now + pd.Timedelta(seconds=state["settings"].stale_after_s + 30))
    assert snap.stale and snap.aqi.value is None and snap.eff_pm25.value is None
    assert "stale_data" in set(snap.open_alerts["rule_key"])


def test_mode_change_is_logged(state):
    assert change_mode(state, "BOOST", pd.Timestamp.now())
    ev = state["store"].events(limit=5)
    assert ev["message"].str.contains("AUTO → BOOST").any()


def test_alert_not_duplicated_on_rerun(state):
    now = pd.Timestamp.now()
    state["adapter"].start_pollution_event(now)
    for i in range(1, 40):
        tick(state, now + pd.Timedelta(seconds=3 * i))
    ev = state["store"].events(limit=500)
    assert (ev["rule_key"] == "pm25_critical").sum() == 1
