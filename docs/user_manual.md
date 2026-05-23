# User Manual

Web dashboard for the Smart Environment Cloud Monitor. Data is loaded from AWS via Flask; warnings and analysis are computed in Lambda.

## Login

1. Start the app: `python run.py`
2. Open http://127.0.0.1:5001/login
3. Register a new user, or sign in with an existing account
4. For local demos only: `DISABLE_AUTH=1` skips login

## Dashboard overview

| Area | Description |
|------|-------------|
| System / Cloud API | Flask and AWS reachability |
| Cloud Data Freshness | Live / Recent / Stale from `latest.timestamp` |
| Sensor backend | Source of latest reading (`sense_emu`, etc.) |
| Last device upload | Relative time from `latest.timestamp` |
| Reading cards | Latest temperature, humidity, pressure |
| Warnings | Active threshold messages |
| Temperature intelligence | Spike, trend, prediction from cloud analysis |
| Chart | Recent temperature vs thresholds |
| Settings form | Saves thresholds to DynamoDB |
| Manual ingest | POST one reading to `/ingest` for testing |

## Refresh rate

The page polls `/api/data` every few seconds (`dataRefreshMs` in `templates/index.html`).

## Warnings

Compared against cloud **settings** for the configured `device_id`:

- Temperature outside `temp_min` / `temp_max`
- Humidity outside `humidity_min` / `humidity_max`
- Pressure outside `pressure_min` / `pressure_max`

If none apply, the banner shows that readings are within normal ranges.

## Analysis panel

- **Spike / drop** — change between the last two temperature samples
- **Trend** — pattern over recent history (stable, increasing, decreasing, volatile)
- **Prediction** — rough estimate of reaching a threshold based on recent slope

Text comes from the `analysis` object in `/api/data` (Lambda).

## Saving settings

Use **Save to cloud**. Values are sent to AWS `POST /settings` and stored under your `device_id` in DeviceSettings.

## Errors

If `/api/data` fails, the banner and status cards show an error. After a successful poll, the last good payload may remain on screen until the next update.
