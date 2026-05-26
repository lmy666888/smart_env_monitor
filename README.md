# Smart Environment Cloud Monitor

Raspberry Pi + Sense HAT environment monitor. Reads temperature, humidity, and pressure from the sensor (or emulator), uploads to AWS via API Gateway, stores in DynamoDB, and shows everything on a Flask dashboard with warnings and trend analysis.

Flask just proxies the cloud API — all the analysis logic runs in Lambda.

## How it works

```
Sense HAT / Emulator
        │
        │  device/emulator_uploader.py
        │  (POST /ingest with X-DEVICE-KEY header)
        ▼
API Gateway → Lambda ingest_sensor_data → DynamoDB SensorData
                                               │
API Gateway → Lambda get_dashboard_data ◀──────┘
                │  warnings, trend, spike detection, prediction
                │  SNS email alert if thresholds exceeded
                ▼
Flask /api/data (proxies GET /data, requires login)
                │
                ▼
Browser (Chart.js, polls every 4 seconds)
```

## Tech stack

| Layer | What |
|-------|------|
| Device | Raspberry Pi + Sense HAT, or `sense_emu` on desktop |
| Cloud | API Gateway HTTP API, Lambda (Python), DynamoDB |
| Dashboard | Flask, Jinja2, Chart.js |
| Alerts | SNS email (optional) |

## Sensor ranges

These are the accepted ranges across the whole stack (Lambda, uploader, frontend validation):

| Metric | Range | Unit |
|--------|-------|------|
| Temperature | -40 to 100 | °C |
| Humidity | 0 to 100 | % |
| Pressure | 800 to 1200 | hPa |

Readings outside these ranges get rejected by `ingest_sensor_data`.

## Project layout

```
api/            Flask routes, auth, pages
cloud/          HTTP client that talks to API Gateway
config/         .env loading, URLs, feature flags
device/         Uploaders (emulator, mock, Pi)
lambda/         Lambda source — zip these with shared/ to deploy
  shared/       Warnings, analysis, settings, SNS alerts
sensor/         Sense HAT reader
services/       AWS proxy layer (Flask just passes data through)
templates/      HTML (dashboard + login page)
static/         JS and CSS
infrastructure/ CloudFormation snippet for /settings route
run.py          Start Flask
```

## Setup

### 1. Clone and install

```bash
cd ~/Desktop
git clone <your-repo-url> smart_env_monitor
cd smart_env_monitor

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

You might also need the Sense HAT emulator package:

```bash
pip install sense-emu sense-hat
```

### 2. Create your .env

`.env` is not in git (it has your API key). You have to create it yourself:

```bash
cp .env.example .env
nano .env
```

At minimum, set these two:

```
AWS_API_BASE_URL=https://your-api-id.execute-api.ap-southeast-2.amazonaws.com
DEVICE_API_KEY=your-device-api-key
```

The `DEVICE_API_KEY` must match the value set on the `ingest_sensor_data` Lambda in AWS Console.

### Full list of .env variables

| Variable | Default | What it does |
|----------|---------|-------------|
| `SECRET_KEY` | `change-me-in-production` | Flask session secret |
| `FLASK_ENV` | `production` | Set to `development` for debug mode |
| `AWS_API_BASE_URL` | — | Your API Gateway URL (no trailing slash) |
| `AWS_REGION` | `ap-southeast-2` | AWS region |
| `DEVICE_API_KEY` | — | Shared secret, sent as `X-DEVICE-KEY` header |
| `DEVICE_ID` | `pi-001` | Partition key in DynamoDB |
| `SENSOR_INTERVAL` | `5` | Seconds between readings |
| `SENSOR_BACKEND` | `sense_emu` | Or `real_sense_hat` on a real Pi |
| `ENABLE_BACKGROUND_COLLECTOR` | `false` | Usually leave off, use the uploader script instead |
| `DISABLE_AUTH` | `0` | Skips login, only works when `FLASK_ENV=development` |
| `CLOUD_TIMEOUT_SECONDS` | `12` | HTTP timeout for API calls |

Lambda-side variables (set in AWS Console, not in `.env`):

| Variable | Which Lambda |
|----------|-------------|
| `SENSOR_TABLE_NAME` | ingest + dashboard |
| `SETTINGS_TABLE_NAME` | dashboard + settings |
| `USERS_TABLE_NAME` | auth |
| `DEVICE_API_KEY` | ingest |
| `SNS_TOPIC_ARN` | dashboard |

## Running the project (three terminals)

You need three terminals open at the same time.

**Terminal 1 — Emulator GUI**

```bash
cd ~/Desktop/smart_env_monitor
source .venv/bin/activate
sense_emu_gui
```

If `sense_emu_gui` isn't found, try `python3 -m sense_emu.gui`.

Once it opens, drag the sliders to reasonable values — Temperature around 25, Humidity around 55, Pressure around 1013. If you leave them at zero the uploader will reject the readings.

**Terminal 2 — Uploader**

```bash
cd ~/Desktop/smart_env_monitor
source .venv/bin/activate
PYTHONPATH=. python3 device/emulator_uploader.py
```

Working output looks like:

```
[POST] source=sense_emu T=25.12°C H=54.80% P=1013.25 hPa → HTTP 201
```

If you see HTTP 403, your `DEVICE_API_KEY` doesn't match what's on the Lambda.

**Terminal 3 — Dashboard**

```bash
cd ~/Desktop/smart_env_monitor
source .venv/bin/activate
PYTHONPATH=. python3 run.py
```

Go to http://127.0.0.1:5001, register a user, log in. The dashboard polls `/api/data` every few seconds and shows the latest readings from DynamoDB.

## API routes

API Gateway routes (Lambda backend):

| Route | Method | Handler |
|-------|--------|---------|
| `/ingest` | POST | `ingest_sensor_data` |
| `/data` | GET | `get_dashboard_data` |
| `/settings` | GET, POST | `settings_handler` |
| `/login` | POST | `auth_handler` |
| `/register` | POST | `auth_handler` |
| `/health` | GET | `health_check` |

Flask proxies these under `/api/*` (e.g. `/api/data` calls `/data` on API Gateway).

## Analysis

`get_dashboard_data` Lambda does all the analysis — Flask doesn't compute any of this:

- **Warnings** — checks latest reading against the saved thresholds in DeviceSettings
- **Spike/drop** — compares last two temperature readings (threshold default 3°C)
- **Trend** — looks at recent readings to determine stable / rising / falling / volatile
- **Prediction** — simple linear projection of when temp might cross a threshold

## SNS email alerts

Optional. If you set `SNS_TOPIC_ARN` on the `get_dashboard_data` Lambda, it will publish an email when warnings reach `warning` or `critical` level. There's a 10-minute cooldown per device so you don't get spammed. You can also create an `AlertState` DynamoDB table (PK: `alert_key`) to persist the cooldown across cold starts, but it works without it too.

## Troubleshooting

**HTTP 403 / DEVICE_KEY_FORBIDDEN when uploading**

Your `DEVICE_API_KEY` is wrong or missing. Check `.env`, make sure it matches what's set on the Lambda in AWS Console. Quick test:

```bash
source .env
curl -s -X POST "$AWS_API_BASE_URL/ingest" \
  -H "Content-Type: application/json" \
  -H "X-DEVICE-KEY: $DEVICE_API_KEY" \
  -d '{"device_id":"pi-001","temperature":25,"humidity":55,"pressure":1013,"source":"curl_test"}'
```

**No .env file after cloning**

That's expected — `.env` is in `.gitignore` because it has secrets. Create it from the example: `cp .env.example .env`

**Emulator GUI won't open**

Usually means `sense-emu` isn't installed or there's no display. Try:

```bash
pip install sense-emu sense-hat
export DISPLAY=:0
sense_emu_gui
```

On a headless Pi you need VNC or a monitor connected.

**Emulator returns garbage values (T=0, H=16172, P=0)**

This happens when the emulator process is stale or the GUI didn't connect properly. Kill everything and start fresh:

```bash
pkill -f sense_emu
pkill -f sense_emu_gui
pkill -f emulator_uploader
```

Reopen the GUI, set the sliders to normal values, then restart the uploader.

**ModuleNotFoundError: No module named 'cloud'**

You're not in the project root, or `PYTHONPATH` isn't set. Always run from the project directory:

```bash
cd ~/Desktop/smart_env_monitor
PYTHONPATH=. python3 device/emulator_uploader.py
```

**Dashboard shows no data / "Unknown" freshness**

Either the uploader isn't getting 201s, or `AWS_API_BASE_URL` is wrong, or there's no data in DynamoDB for your device ID. Check directly:

```bash
source .env
curl -s "$AWS_API_BASE_URL/data?device_id=pi-001" | python3 -m json.tool
```

If `sensor_data` is empty, the uploader isn't reaching DynamoDB. Check CloudWatch logs.

**Settings don't save / 404 on POST /settings**

The `/settings` route might not be deployed on your API Gateway. See `infrastructure/AWS_HTTP_API_SETTINGS_ROUTES.md` for the CloudFormation template to add it.

## Testing checklist

- [ ] Emulator opens and sliders work
- [ ] Uploader prints HTTP 201
- [ ] DynamoDB shows new `pi-001` entries
- [ ] Dashboard shows live data
- [ ] Can save threshold settings
- [ ] Warnings appear when values exceed thresholds
- [ ] Temperature thresholds work from -40 to 100
- [ ] Pressure thresholds work from 800 to 1200
- [ ] Manual ingest form works
- [ ] `.env` is not in git

## Deploying to AWS

1. Create DynamoDB tables: `SensorData` (PK `device_id`, SK `timestamp`), `DeviceSettings` (PK `device_id`), `Users` (PK `username`)
2. Zip each Lambda with `shared/` at the zip root and upload
3. Create API Gateway HTTP API, add routes pointing to each Lambda (`AWS_PROXY` integration, payload format 2.0)
4. Set Lambda env vars: `SENSOR_TABLE_NAME`, `SETTINGS_TABLE_NAME`, `USERS_TABLE_NAME`, `DEVICE_API_KEY`
5. Put the API Gateway URL in your `.env` as `AWS_API_BASE_URL`

## Note

All warnings and analysis come from `get_dashboard_data` Lambda only. Flask doesn't do any local analysis — it just forwards what Lambda returns.
