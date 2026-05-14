# User Manual

The Smart Environment Monitoring System dashboard shows real-time
temperature, humidity, and pressure readings collected by a Raspberry Pi
device and stored in AWS.

## 1. Logging in

1. Start Flask (`python run.py`), then open **http://127.0.0.1:5001/login** (or `/` redirect).
2. Enter the demo credentials: `admin / admin123` (unless `DISABLE_AUTH=1`).
3. You will be redirected to `/dashboard`.

> Session-based login is enforced by Flask when auth is enabled; `DISABLE_AUTH` is for trusted local demos only.

## 2. Dashboard sections

| Section | What it shows |
|---|---|
| System / cloud status | Local Flask health and cloud reachability indicators. |
| Warning level | Normal / warning / critical from threshold logic. |
| Reading cards | Latest temperature, humidity, pressure from cloud payload. |
| Warnings | Active threshold violations. |
| Temperature intelligence | Spike/trend/prediction from `services/analysis_service`. |
| Historical chart | Temperature series from recent `sensor_data`. |
| Threshold form | Persists to AWS via `/api/settings` when configured. |

## 3. Refresh cadence

Polling interval is set in `templates/index.html` (`window.APP_CONFIG.dataRefreshMs`, default a few seconds). Adjust there for demos or recordings.

## 4. Warning rules

Given the AWS `settings`, a warning is produced when the latest reading is:

- `temperature < temp_min` or `temperature > temp_max`
- `humidity < humidity_min` or `humidity > humidity_max`
- `pressure < pressure_min` or `pressure > pressure_max`

If none apply, the banner shows **"All readings are within normal ranges."**

## 5. Trend analysis

- **Spike / drop**: the difference between the two most recent temperature
  values; flagged if the change exceeds ±3 °C by default.
- **Trend**: the total change across all loaded readings; classified as
  "increasing", "decreasing" or "stable" using a ±0.5 °C delta.
- **Summary**: minimum / maximum temperature observed in the loaded window.

## 6. Error handling

- Failed `/api/data` polls surface in the warning banner and status cards; transient failures may keep the last good payload on screen until the next successful refresh.
