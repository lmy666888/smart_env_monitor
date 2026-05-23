# Smart Environment Cloud Monitor

IoT environment monitoring for a Raspberry Pi–class device. Sensor readings are stored in **AWS DynamoDB**; **Lambda** computes warnings, trends, and predictions. A **Flask** app provides the dashboard and proxies API Gateway (BFF + session auth).

## Features

- Live dashboard: temperature, humidity, pressure, historical chart
- Threshold warnings (temp / humidity / pressure) from cloud settings
- Trend, spike/drop, and threshold-crossing prediction (Lambda analysis)
- Device settings saved to DynamoDB via API Gateway
- Login and registration (Users table in DynamoDB)
- Sense HAT Emulator or Pi ingest via HTTP POST `/ingest`
- Optional local fallback when AWS is unreachable (`LOCAL_FALLBACK_ON_AWS_ERROR`)

## Architecture

```
Sense HAT / sense_emu / device uploaders
        │  POST /ingest  (JSON + source field)
        ▼
API Gateway  →  ingest_sensor_data  →  DynamoDB SensorData
                        │
                        ▼
              get_dashboard_data (warnings, analysis, settings, chart)
                        │
        GET /data         │
        ▼                 │
Flask /api/data ─────────┘  →  Browser (Chart.js)
```

Flask is a **BFF only**: warnings, trend, and prediction are computed exclusively in **`get_dashboard_data` Lambda** (`source: aws_lambda`).

## Tech stack

| Layer | Technology |
|-------|------------|
| Device | Raspberry Pi, Sense HAT, `sense_emu`, optional mock uploader |
| Ingest / API | API Gateway (HTTP), Lambda (Python 3.x) |
| Storage | DynamoDB (SensorData, DeviceSettings, Users) |
| Dashboard | Flask, Jinja2, vanilla JS, Chart.js |
| Ops | CloudWatch (recommended), curl for smoke tests |

## AWS components

| Resource | Purpose |
|----------|---------|
| **SensorData** | `device_id` + `timestamp` — all readings |
| **DeviceSettings** | Per-device threshold min/max |
| **Users** | `username`, `email`, `password_hash` for auth |
| **ingest_sensor_data** | Validate POST body, write SensorData |
| **get_dashboard_data** | Latest + history, warnings, analysis, chart series |
| **settings_handler** | GET/POST device thresholds |
| **auth_handler** | POST `/login`, `/register` |
| **health_check** | GET `/health` |

Default region in docs/examples: `ap-southeast-2`. Base URL is set in `.env` (`AWS_API_BASE_URL`).

## Project layout

```
api/            Flask blueprints (/api/*, pages, auth session)
cloud/          HTTP client for API Gateway
config/         Settings and cloud URLs
device/         Standalone uploaders (emulator, mock demo, Pi sender)
docs/           Setup, user manual, troubleshooting, test plan
infrastructure/ API Gateway route notes + sample CloudFormation
lambda/         Lambda source (deploy as zip; includes shared/)
sensor/         Reader, optional background collector
services/       AWS proxy, cloud brain enrichment, local fallback
templates/      Dashboard and login HTML
static/         CSS and dashboard JS
legacy/         Optional SQLite cache and Sense HAT LED helpers
run.py          Local entrypoint
```

## Setup

**Prerequisites:** Python 3.10+, browser, AWS API Gateway endpoints already deployed (or your own stack).

```bash
cd smart_env_monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit SECRET_KEY and AWS_API_BASE_URL if needed
python run.py
```

1. Open http://127.0.0.1:5001/login — register, then sign in (auth required in production).
2. Dashboard polls `GET /api/data`, which calls AWS `GET /data`.

## Running with Sense HAT Emulator (recommended demo)

Use **system Python** for the emulator uploader so the Flask venv does not post invalid emulator reads as mock data.

**Terminal 1 — emulator GUI**

```bash
python3 -m sense_emu.gui
```

**Terminal 2 — upload to AWS (`source=sense_emu`)**

```bash
cd smart_env_monitor
python3 device/emulator_uploader.py
```

**Terminal 3 — dashboard (no background collector)**

```bash
source .venv/bin/activate
ENABLE_BACKGROUND_COLLECTOR=false python run.py
```

Browser: http://127.0.0.1:5001

## Configuration (common)

| Variable | Default | Notes |
|----------|---------|--------|
| `DEVICE_API_KEY` | — | Shared secret; sent as `X-DEVICE-KEY` on POST `/ingest` |
| `SNS_TOPIC_ARN` | — | Lambda env: email alerts on warning/critical |
| `ENABLE_BACKGROUND_COLLECTOR` | `false` | Off = cloud-only ingest via device scripts |
| `DEVICE_ID` | `pi-001` | DynamoDB partition key for device |
| `DEMO_MODE` / `MOCK_UPLOAD_ENABLED` | `false` | Required for `device/mock_uploader.py` |
| `LOCAL_FALLBACK_ON_AWS_ERROR` | `false` | Local analysis if `/data` fails |
| `USE_SQLITE_CACHE` | `false` | Optional mirror to SQLite (`legacy/`) |

See `.env.example` and `config/cloud_config.py` for URLs and timeouts.

## API endpoints

### API Gateway (production)

| Route | Method | Lambda |
|-------|--------|--------|
| `/ingest` | POST | `ingest_sensor_data` |
| `/data` | GET | `get_dashboard_data` |
| `/settings` | GET, POST | `settings_handler` |
| `/login` | POST | `auth_handler` |
| `/register` | POST | `auth_handler` |
| `/health` | GET | `health_check` |

### Flask proxy

| Flask | AWS |
|-------|-----|
| `GET /api/data` | `GET /data` |
| `POST /api/ingest` | `POST /ingest` |
| `GET/POST /api/settings` | `GET/POST /settings` |
| `POST /api/login`, `/api/register` | same |
| `GET /api/health` | `GET /health` |

## Smart analysis (Lambda)

Computed in `get_dashboard_data` using recent SensorData and DeviceSettings:

- **Warnings** — latest reading vs thresholds
- **Spike/drop** — last two temperature points vs `SPIKE_THRESHOLD`
- **Trend** — recent window (stable / increasing / decreasing / volatile)
- **Prediction** — simple linear estimate toward min/max thresholds

## Dashboard

- Status cards: cloud API, data freshness (`latest.timestamp`), sensor backend (`source` from cloud)
- Warning level, list, and banner
- Temperature intelligence panel (analysis from `/data`)
- Historical temperature chart with threshold lines
- Save thresholds to cloud; manual ingest form for testing

Polling interval: `window.APP_CONFIG.dataRefreshMs` in `templates/index.html` (default 4s).

## AWS deployment overview

1. Create DynamoDB tables (keys as above).
2. Deploy each Lambda from `lambda/` (include `shared/` in the zip root).
3. Wire API Gateway HTTP routes to Lambda ARNs (`AWS_PROXY`, payload 2.0).
4. Set Lambda env vars: `SENSOR_TABLE_NAME`, `SETTINGS_TABLE_NAME`, `USERS_TABLE_NAME`, etc.
5. Point Flask `.env` at the execute-api base URL.

See `infrastructure/AWS_HTTP_API_SETTINGS_ROUTES.md` for adding `/settings` routes to an existing API.

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Blank dashboard | DevTools → `/api/data`; CloudWatch on `get_dashboard_data` |
| Settings revert to defaults | DeviceSettings key must be `device_id`; redeploy settings Lambdas |
| Stale “Sensor Backend” | Hard-refresh browser; confirm `latest.source` in `/data` JSON |
| Ingest 4xx | CloudWatch on `ingest_sensor_data`; validate numeric fields |
| POST /settings 404 | Missing API route — see `infrastructure/` |

More detail: [docs/troubleshooting.md](docs/troubleshooting.md).

## Screenshots (submission)

Add figures here for your report, for example:

1. Architecture diagram (device → API Gateway → Lambda → DynamoDB → Flask → browser)
2. Dashboard overview with live readings
3. Warnings active after lowering thresholds
4. AWS Console: DynamoDB item with `source: sense_emu`
5. Temperature intelligence and chart panels

## SNS email alerts

Set on **`get_dashboard_data` Lambda** (not Flask):

- `SNS_TOPIC_ARN` — subscribe your email to the topic in AWS Console
- `ALERT_COOLDOWN_SECONDS` — default 600 (10 minutes per device/level)
- `ALERT_STATE_TABLE_NAME` — optional DynamoDB table (partition key `alert_key`) for cooldown across Lambda cold starts

## Future improvements

- MQTT / AWS IoT Core ingest path
- Per-user device ownership in DynamoDB
- Automated tests against mocked API Gateway responses
- Infrastructure as Code for the full stack (not only settings routes)

## Further reading

- [docs/setup_guide.md](docs/setup_guide.md)
- [docs/user_manual.md](docs/user_manual.md)
- [docs/test_plan.md](docs/test_plan.md)

## Assignment note

Authoritative warnings and analysis come only from **`get_dashboard_data` Lambda** (`analysis_source: aws_lambda`). Flask does not import `lambda/shared` for brain logic.
