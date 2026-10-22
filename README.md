# AeroGuard — Smart Public Air Filtration Tower

**AeroGuard | Intelligent Environmental Monitoring System** — a competition-concept dashboard that shows the
tower's three jobs:

| | |
|---|---|
| **MEASURE** | Ambient PM2.5 / PM10, temperature, humidity, airflow, filter ΔP, power |
| **RESPOND** | ECO / AUTO / BOOST supervisory fan control with smoothing, hysteresis and ramp limits |
| **PROVE**   | Paired inlet/outlet removal efficiency, CADR, clean air delivered, energy per clean air |

> The app runs in **demo mode**: every value comes from a seeded simulator, and a small note on the
> Overview page says so. No hardware is connected and no motor is actuated.

---

## Quick start

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501.

Always start it with `streamlit run app.py`, not `python app.py`. Running it with plain Python prints
"missing ScriptRunContext" warnings and nothing appears.

### Windows notes

* If PowerShell refuses to run `Activate.ps1`, allow local scripts for your user once:
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Or skip activation and call the venv's Python
  directly: `.venv\Scripts\python.exe -m streamlit run app.py`.
* **Long paths:** some packages (e.g. Plotly) contain very deep file paths. If `pip install` fails with
  *"No such file or directory … Windows Long Path support"*, either enable long paths in Windows or create the
  venv somewhere short, e.g.
  `python -m venv C:\venvs\aeroguard` then `C:\venvs\aeroguard\Scripts\python.exe -m pip install -r requirements.txt`
  and `C:\venvs\aeroguard\Scripts\python.exe -m streamlit run app.py`.
* Use a virtual environment rather than your global Python. An older global `protobuf` breaks Streamlit
  (`cannot import name 'builder' from 'google.protobuf.internal'`).

### Run the tests

```bash
python -m pytest -q
```

---

## Live demo script (about 2 minutes)

1. **Overview**: point out the four KPIs and the 24 h trend, which
   includes yesterday's simulated haze episode.
2. Set the trend to **1 h**, then click **Simulate pollution event** (sidebar or control panel).
   Within ~30–60 s PM2.5 climbs past the reference line and AUTO ramps the fan to its maximum.
   The *control reason* explains each step. A critical alert appears; click **Acknowledge**.
3. Click **ECO**: the command is held at the ECO cap, and the reason suggests switching back to AUTO.
   Click **AUTO** again.
4. Click **End event · return to normal**: PM decays and AUTO steps the fan down, with hysteresis
   so it doesn't oscillate.
5. **Filtration Performance**: before/after bars, efficiency history, CADR and the caveats.
6. **Settings → Demo controls → Simulate: Outlet PM sensor offline**: efficiency and CADR become
   *Not available* rather than showing an invented number. Turn it off again.
7. **Malaysia Network**: the national fleet map. Colour by air quality, status or mode, click a tower to
   see its technical view, then use **Regional control** to send ECO / AUTO / BOOST to a whole region or
   start a **regional haze** scenario and watch every tower in that region respond.
8. Optional: **⋮ menu → Settings → Choose app theme → Dark** for a wall-screen look.

All of these actions are recorded in the event log (Overview / Maintenance).

---

## Project structure

```
app.py                     Entry point: page config, state, sidebar, navigation, header/footer
components/
  theme.py                 Design tokens (light + dark), global CSS, Plotly layout
  ui.py                    Header, KPI cards, status badges (icon + text), health list, footer, tables
  schematic.py             Technical cut-away diagram of the tower (SVG) annotated with live values
  charts.py                Plotly charts (one y-axis per chart)
views/
  overview.py              A. Overview
  network.py               Malaysia Network — fleet map, regional control
  live_air.py              B. Live Air Quality
  performance.py           C. Filtration Performance
  energy.py                D. Energy & Sustainability
  maintenance.py           E. Maintenance & System Health
  camera.py                F. Camera / Site Awareness
  settings_page.py         G. Settings / Data Source (+ demo controls)
  common.py                Control panel, alerts panel, pollution-event button, range picker
services/
  fleet.py                 Demo fleet of 25 towers across Malaysia (seeded, time-based)
  sensors.py               SensorAdapter interface + DemoSensorAdapter (seeded, closed-loop simulator)
  control.py               ECO / AUTO / BOOST logic: EMA smoothing, banded hysteresis, ramp limit
  calculations.py          Efficiency, CADR, energy, US EPA AQI (NowCast), ΔP normalisation, validation
  events.py                SQLite event log, state-change alerts with cooldown, maintenance records
  runtime.py               One "tick" per rerun: read → control → alerts → derived metrics
  config.py                Settings dataclass (non-secret), validation, save/load data/settings.json
data/                      aeroguard.db (event log) and settings.json, created at runtime
tests/                     pytest suite for calculations, control and the demo loop
.streamlit/config.toml     Theme and server options
```

---

## Methods and assumptions

| Metric | Method | When it shows "Not available" |
|---|---|---|
| Removal efficiency | `(inlet − outlet) / inlet × 100`, from paired readings | Missing/negative reading, inlet = 0, inlet below the configured minimum (default 2 µg/m³), stale data |
| CADR | `airflow × efficiency / 100` (m³/h, rounded to 10) | Invalid airflow, or efficiency outside 0–100 % |
| PM AQI | **US EPA AQI**, PM2.5 (2024 breakpoints) and PM10, NowCast averaging over 12 h | Fewer than 2 of the last 3 hours available |
| Energy | Trapezoidal integration of power; gaps > 5 min are not filled | Fewer than two samples |
| Filter loading | ΔP scaled to rated airflow (ΔP ∝ flow^1.4) | Airflow < 20 % of rated |

* The AQI shown is the **US EPA** index, not Malaysia's official API (IPU), whose breakpoints differ. Only PM is
  considered.
* Efficiency is a **single-pass** figure for air through the tower. It does not mean the surrounding area is
  cleaner by the same percentage.
* Reference lines on charts (35 µg/m³ PM2.5, 100 µg/m³ PM10) are **configurable operating references**, not
  health limits.
* "Pollution events" = periods where inlet PM2.5 stays at or above the reference for ≥ 5 min (merged when < 10 min
  apart).
* The filter-life figure in hours is a **rough, configurable estimate**. Replacement decisions should follow ΔP.
* No CO₂-emissions-saved claim is made. Adding one would require a disclosed grid emissions factor and baseline.
* The dashboard is supervisory. Motor protection, current limits and interlocks must live in the hardware
  controller.

### Control logic (services/control.py)

1. PM2.5 is smoothed with an exponential moving average (time constant 20 s, configurable).
2. AUTO picks a band (CLEAN / ELEVATED / HIGH / SEVERE). It steps up when the reading crosses a band edge and
   steps down only once it falls `hysteresis` µg/m³ below that edge.
3. Each band maps to a fan command inside the AUTO range. ECO uses the same bands but caps at the ECO limit.
   BOOST requests a fixed level.
4. The command never changes faster than `ramp_pct_per_s` and is always clamped to the hard limits.
5. Modes change only on an explicit operator click, and each change is logged.

---

## Connecting real sensors

The UI only talks to the `SensorAdapter` interface in `services/sensors.py`, so swapping the simulator for real
hardware means writing one class:

```python
# services/esp32_adapter.py
import os, json, serial          # pip install pyserial
import pandas as pd
from services.sensors import SensorAdapter, SensorReading, ComponentHealth, HISTORY_COLUMNS, NORMAL, OFFLINE

class Esp32SerialAdapter(SensorAdapter):
    name = "ESP32 (serial)"
    is_simulated = False
    description = "Readings from the tower controller over USB serial."

    def __init__(self, settings):
        self.settings = settings
        self.port = serial.Serial(os.environ["AEROGUARD_SERIAL_PORT"], 115200, timeout=0.2)
        self.rows = []                      # or write each reading to SQLite

    def latest(self, now):
        line = self.port.readline().decode(errors="ignore").strip()
        if line:
            d = json.loads(line)            # e.g. {"pm25_in": 14.2, "pm25_out": 1.1, ...}
            r = SensorReading(timestamp=pd.Timestamp.now(), inlet_pm25=d.get("pm25_in"),
                              outlet_pm25=d.get("pm25_out"), ..., simulated=False)
            self.rows.append({...})         # one dict per HISTORY_COLUMNS
            self._last = r
        return self._last                   # its timestamp ages → the UI shows stale/offline

    def history(self):
        return pd.DataFrame(self.rows, columns=HISTORY_COLUMNS)

    def health(self, now, settings):
        ...                                 # return ComponentHealth items

    def send_fan_command(self, pct):
        self.port.write(f'{{"fan_cmd": {pct:.0f}}}\n'.encode())
        return "Command sent to tower controller"
```

Then in `services/runtime.py → init_state()` create your adapter instead of `DemoSensorAdapter`. For MQTT, do the
same with `paho-mqtt`: subscribe in a background thread and keep the latest message in memory.

Guidelines:

* Leave any channel you don't have as `None`. The UI then shows **Not available** or **Not Configured**
  automatically.
* Read ports, broker URLs, usernames and passwords from **environment variables**. Never put them in
  `settings.json`, the UI or logs.
* Keep `is_simulated = False` only for real measurements. The demo-mode note follows this flag.
* The hardware controller must enforce its own fan limits, and should ignore commands that fall outside them.
* Calibrate inlet and outlet PM sensors side by side before trusting efficiency values.

---

## Known limitations

* The demo history is regenerated per browser session, seeded and anchored to the current time. The event log
  persists in `data/aeroguard.db`. **Settings → Reset demo data** clears it.
* The theme choice (light / control room) is a Streamlit server option, so all open sessions follow the latest
  choice. This is fine for one demo screen.
* The camera page is a placeholder. No video integration, recording or recognition is implemented.
* This is prototype software, not a certified monitoring instrument.
