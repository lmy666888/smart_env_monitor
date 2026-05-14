# Smart Environment Cloud Monitor (Assignment 2)

Production-style **cloud IoT** stack: Sense HAT / emulator → Python collector → **AWS API Gateway** → **AWS Lambda** → **Amazon DynamoDB** → Flask dashboard. SQLite is **optional cache only** (`USE_SQLITE_CACHE=1`), not the system of record.

---

## Architecture

```
┌─────────────────────┐     HTTPS POST JSON      ┌──────────────────┐
│  Sense HAT / emu    │ ──── ingest (/ingest) ─► │  API Gateway     │
│  + sensor.reader    │                          └────────┬─────────┘
└─────────────────────┘                                   │
         ▲                                                ▼
         │                                        ┌─────────────────┐
         │  same host: Flask worker thread        │  Lambda ingest  │
         └──────────── collect_reading_and_upload │  → DynamoDB     │
                                                  └─────────────────┘
                                                           │
  Browser ◄──── polling GET /api/data ─── Flask ─────────┘
                (server calls AWS GET /data)
```

**Why Flask calls AWS instead of the browser alone?** Keeps your Assignment 1 **session login** model, avoids CORS surprises for authenticated JSON, and centralises timeouts/retries in Python (`cloud/client.py`). The dashboard still shows **live** DynamoDB-backed data because `/api/data` proxies the cloud on every refresh.

---

## Quick start

```bash
cd smart_env_monitor
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DISABLE_AUTH=1       # optional: skip login for local demos
python run.py               # or: python legacy/app.py
```

Open **http://127.0.0.1:5001/dashboard** (default port avoids macOS AirPlay on 5000).

---

## AWS endpoints (class deployment)

| Purpose | Method | URL |
|--------|--------|-----|
| Ingest sensor readings | `POST` | `https://9jzbd9a34j.execute-api.ap-southeast-2.amazonaws.com/ingest` |
| Dashboard payload | `GET` | `https://9jzbd9a34j.execute-api.ap-southeast-2.amazonaws.com/data` |
| Threshold settings | `GET`, `POST` | `https://9jzbd9a34j.execute-api.ap-southeast-2.amazonaws.com/settings` |

If **Save to cloud** returns 502 with `AWS_SETTINGS_ROUTE_NOT_FOUND`, API Gateway is missing these routes — deploy using **`infrastructure/httpapi-settings-routes.yaml`** (CloudFormation) or follow **`infrastructure/AWS_HTTP_API_SETTINGS_ROUTES.md`**. Lambda handler: **`settings_handler.lambda_handler`** (package `settings_handler.py` + `shared/dynamo_settings.py` in the deployment zip).

Override with environment variables (see `config/settings.py`):

- `AWS_API_BASE` — base URL without trailing slash  
- `AWS_INGEST_URL`, `AWS_DATA_URL`, `AWS_SETTINGS_URL` — full URLs if paths differ  
- `DEVICE_ID` — default `pi-001` (must match DynamoDB partition key)  
- `SENSOR_INTERVAL` — seconds between **automatic** uploads from the Flask background worker  

---

## Project layout (Assignment 2)

| Path | Role |
|------|------|
| `api/` | Flask factory (`create_app`), JSON routes (`api/routes.py`), HTML routes (`api/pages.py`), auth |
| `cloud/` | `CloudAPIClient` — `requests`, retries, timeouts |
| `sensor/` | `reader.py` (HAT/emu/mock), `collector.py` (ingest + optional SQLite) |
| `device/` | Standalone uploader for Pi / dev machine (`python -m device.device_sender`) |
| `services/` | Warnings, trend analysis, dashboard payload assembly |
| `config/` | Centralised settings + `.env` loading |
| `utils/` | Logging helpers |
| `templates/`, `static/` | Dashboard UI |
| `lambda/` | Reference serverless handlers deployed behind API Gateway |
| `legacy/` | SQLite helpers, Sense HAT **LED** bridge (optional) |

Standalone Pi sender (no Flask): `python -m device.device_sender`

---

## JSON contracts

**Ingest (POST)** — body:

```json
{
  "device_id": "pi-001",
  "temperature": 23.4,
  "humidity": 55.2,
  "pressure": 1013.25
}
```

**Data (GET)** — response (simplified):

```json
{
  "sensor_data": [
    {
      "device_id": "pi-001",
      "temperature": 23.4,
      "humidity": 55.2,
      "pressure": 1013.25,
      "timestamp": "2026-05-14T12:00:00.000000+00:00"
    }
  ],
  "settings": {
    "temp_min": 0,
    "temp_max": 40,
    "humidity_min": 20,
    "humidity_max": 80,
    "pressure_min": 980,
    "pressure_max": 1030
  }
}
```

---

## Reliability & engineering features

- **Retries**: `urllib3.Retry` on the `requests` session for transient 5xx/429 and connection errors (`HTTP_MAX_RETRIES`, `HTTP_RETRY_BACKOFF`).  
- **Timeouts**: `HTTP_TIMEOUT_SECONDS`, `DASHBOARD_CLOUD_TIMEOUT`.  
- **Logging**: structured module loggers (`smart_env_monitor.*`).  
- **Health**: `GET /health` (process) and `GET /api/health` (includes quick cloud ping).  
- **Graceful degradation**: `/api/data` returns 200 with empty charts and clear messages if AWS is down.  
- **SQLite**: enable only with `USE_SQLITE_CACHE=1` for local mirror/debug.

---

## Assignment 2 technical summary

1. **Cloud ingestion** — Background thread + optional `device_sender` use `requests` POST to `/ingest` with JSON, retries, and timeouts.  
2. **DynamoDB as source of truth** — Dashboard reads via `GET /data`; SQLite is not primary.  
3. **Frontend** — Modern responsive UI, cloud/DynamoDB/upload indicators, loading overlay, empty state, threshold warnings with **normal / warning / critical** levels.  
4. **API layer** — `CloudAPIClient` isolates HTTP; Flask routes stay thin.  
5. **Config** — `config/` package + environment variables for all AWS URLs and behaviour.  
6. **Pi & emulator** — Unchanged `sensor.reader` behaviour: Sense HAT emulator preferred, hardware on Pi, deterministic mock if hardware fails (with throttled warnings in logs).

---

## Security note

Set a strong `SECRET_KEY` and prefer `ADMIN_PASSWORD_HASH` (Werkzeug) in production. Use `DISABLE_AUTH=1` only on trusted networks.
