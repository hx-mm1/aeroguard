import pandas as pd

from services.config import Settings
from services.fleet import FLEET, OFFLINE, fleet_status

NOW = pd.Timestamp("2026-10-22 09:00")
LIVE = {"site": "Main Lobby", "status": "Online", "note": "", "mode": "AUTO", "pm25": 14.0, "pm10": 26.0,
        "fan_pct": 48, "efficiency": 92.0, "airflow": 2780, "power_w": 150, "dp_pa": 226}


def test_fleet_covers_all_towers_with_unique_ids():
    df = fleet_status(NOW, Settings(), {}, set(), LIVE)
    assert len(df) == len(FLEET) == df["tower_id"].nunique()
    assert df["lat"].between(0.8, 7.5).all() and df["lon"].between(99.5, 119.5).all()  # inside Malaysia


def test_live_tower_mirrors_dashboard():
    row = fleet_status(NOW, Settings(), {}, set(), LIVE).set_index("tower_id").loc["AG-001"]
    assert row["pm25"] == 14.0 and row["site"] == "Main Lobby"


def test_offline_tower_reports_no_values():
    df = fleet_status(NOW, Settings(), {}, set(), LIVE)
    off = df[df["status"] == OFFLINE]
    assert not off.empty and off["pm25"].isna().all()


def test_haze_raises_pm_and_auto_fan_in_region_only():
    s = Settings()
    base = fleet_status(NOW, s, {}, set(), LIVE).set_index("tower_id")
    hazy = fleet_status(NOW, s, {}, {"Sabah"}, LIVE).set_index("tower_id")
    assert hazy.loc["AG-023", "pm25"] > base.loc["AG-023", "pm25"] + 30
    assert hazy.loc["AG-023", "fan_pct"] > base.loc["AG-023", "fan_pct"]
    assert hazy.loc["AG-009", "pm25"] == base.loc["AG-009", "pm25"]


def test_modes_respect_limits():
    s = Settings()
    df = fleet_status(NOW, s, {"AG-023": "BOOST", "AG-024": "ECO"}, {"Sabah"}, LIVE).set_index("tower_id")
    assert df.loc["AG-023", "fan_pct"] == s.boost_pct
    assert df.loc["AG-024", "fan_pct"] <= s.eco_cap_pct
