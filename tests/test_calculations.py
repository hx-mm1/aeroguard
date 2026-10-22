import math

import numpy as np
import pandas as pd
import pytest

from services import calculations as calc


# --- removal efficiency -------------------------------------------------------

def test_efficiency_basic():
    r = calc.removal_efficiency(40.0, 2.0)
    assert r.value == 95.0 and r.message == ""


@pytest.mark.parametrize("inlet,outlet", [(None, 1), (10, None), (float("nan"), 1), (10, float("inf")), ("x", 1), (True, 1)])
def test_efficiency_missing_or_invalid(inlet, outlet):
    assert calc.removal_efficiency(inlet, outlet).value is None


def test_efficiency_zero_inlet():
    r = calc.removal_efficiency(0, 0)
    assert r.value is None and "zero" in r.message


def test_efficiency_negative_reading():
    assert calc.removal_efficiency(-1, 0).value is None
    assert calc.removal_efficiency(10, -0.5).value is None


def test_efficiency_below_min_inlet():
    r = calc.removal_efficiency(1.5, 0.1, min_inlet=2.0)
    assert r.value is None and "too low" in r.message


def test_efficiency_outlet_above_inlet_not_clamped():
    r = calc.removal_efficiency(10, 12)
    assert r.value == -20.0
    assert "exceeds" in r.message


def test_efficiency_series_marks_invalid_as_nan():
    s = calc.efficiency_series(pd.Series([10, 0, None, 10, 1]), pd.Series([1, 0, 1, None, 0.5]), min_inlet=2)
    assert s.iloc[0] == pytest.approx(90.0)
    assert s.iloc[1:].isna().all()


# --- CADR ------------------------------------------------------------------------

def test_cadr_valid():
    assert calc.cadr(3000, 92.0).value == 2760.0


@pytest.mark.parametrize("airflow,eff", [(None, 90), (0, 90), (-5, 90), (3000, None), (3000, -10), (3000, 0), (3000, 101)])
def test_cadr_invalid(airflow, eff):
    assert calc.cadr(airflow, eff).value is None


def test_cadr_rounding_avoids_false_precision():
    assert calc.cadr(2781, 92.07).value == 2560.0


# --- energy ------------------------------------------------------------------------

def test_energy_constant_power_one_hour():
    ts = pd.date_range("2026-01-01", periods=61, freq="1min")
    assert calc.energy_kwh(ts, [1000.0] * 61).value == pytest.approx(1.0)


def test_energy_skips_long_gaps():
    ts = list(pd.date_range("2026-01-01 00:00", periods=31, freq="1min")) + \
         list(pd.date_range("2026-01-01 02:00", periods=31, freq="1min"))
    r = calc.energy_kwh(ts, [600.0] * 62)
    assert r.value == pytest.approx(0.6)  # two 30-min blocks at 600 W; the 1.5 h gap is not invented
    assert "Only" in r.message


def test_energy_handles_nan_and_short_input():
    assert calc.energy_kwh([pd.Timestamp("2026-01-01")], [5]).value is None
    ts = pd.date_range("2026-01-01", periods=3, freq="1min")
    assert calc.energy_kwh(ts, [np.nan, np.nan, np.nan]).value is None


def test_specific_energy():
    assert calc.specific_energy_wh_per_1000m3(2.0, 40000).value == 50.0
    assert calc.specific_energy_wh_per_1000m3(2.0, 0).value is None


# --- AQI ------------------------------------------------------------------------------

@pytest.mark.parametrize("conc,expected", [(0, 0), (9.0, 50), (9.1, 51), (35.4, 100), (35.5, 101), (55.4, 150),
                                           (125.4, 200), (225.4, 300), (325.4, 500)])
def test_aqi_pm25_breakpoints(conc, expected):
    assert calc.aqi_pm25(conc) == expected


def test_aqi_pm25_truncates():
    assert calc.aqi_pm25(9.09) == 50  # truncated to 9.0, not rounded to 9.1


@pytest.mark.parametrize("conc,expected", [(54, 50), (55, 51), (154, 100), (155, 101), (604, 500)])
def test_aqi_pm10_breakpoints(conc, expected):
    assert calc.aqi_pm10(conc) == expected


def test_aqi_invalid_and_categories():
    assert calc.aqi_pm25(None) is None and calc.aqi_pm25(-1) is None
    assert calc.aqi_category(42) == "Good"
    assert calc.aqi_category(101) == "Unhealthy for Sensitive Groups"
    assert calc.aqi_category(None) is None


def test_nowcast_constant_and_requirements():
    assert calc.nowcast([20.0] * 12) == pytest.approx(20.0)
    assert calc.nowcast([None, None, 10, 10]) is None  # needs 2 of the 3 most recent hours
    assert calc.nowcast([30, None, 10]) is not None


def test_nowcast_weights_recent_hours_more():
    rising = calc.nowcast([60, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20])
    assert 20 < rising < 60 and rising > sum([60] + [20] * 11) / 12


def test_aqi_from_history_uses_both_pollutants():
    now = pd.Timestamp("2026-01-01 12:00")
    ts = pd.date_range(now - pd.Timedelta(hours=12), now, freq="1min")
    df = pd.DataFrame({"timestamp": ts, "inlet_pm25": 5.0, "inlet_pm10": 200.0})
    r = calc.aqi_from_history(df, now)
    assert r.dominant == "PM10" and r.value == calc.aqi_pm10(200)


# --- filter, episodes, freshness, formatting --------------------------------------------

def test_normalised_dp():
    assert calc.normalised_dp(100, 3000, 6000) == pytest.approx(100 / 0.5 ** 1.4)
    assert calc.normalised_dp(100, 500, 6000) is None  # below 20 % rated airflow
    assert calc.normalised_dp(None, 3000, 6000) is None


def test_count_exceedance_episodes():
    ts = pd.date_range("2026-01-01", periods=120, freq="1min")
    vals = np.full(120, 10.0)
    vals[10:30] = 50   # episode 1 (20 min)
    vals[35:40] = 50   # merges with episode 1 (gap 5 min < 10)
    vals[80:82] = 50   # too short, ignored
    vals[95:110] = 50  # episode 2
    df = pd.DataFrame({"timestamp": ts, "pm": vals})
    assert calc.count_exceedance_episodes(df, "pm", 35) == 2


def test_is_stale_and_fmt():
    now = pd.Timestamp("2026-01-01 12:00:00")
    assert calc.is_stale(now - pd.Timedelta(seconds=200), now, 120)
    assert not calc.is_stale(now - pd.Timedelta(seconds=30), now, 120)
    assert calc.is_stale(None, now, 120)
    assert calc.fmt(None) == "Not available"
    assert calc.fmt(math.nan) == "Not available"
    assert calc.fmt(1234.56, 1, "m³/h") == "1,234.6 m³/h"
