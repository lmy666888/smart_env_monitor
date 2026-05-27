# Smart Environment Cloud Monitor

Assignment 2 — IoT + cloud environmental monitoring.

A Raspberry Pi (or Sense HAT emulator) reads temperature, humidity, and pressure, uploads readings to AWS, and shows them on a Flask dashboard. Warnings, trends, and alerts run in Lambda — Flask mostly just forwards requests to API Gateway.

## Features

- Live dashboard with Chart.js (polls every ~4 seconds)
- Cloud storage in DynamoDB (`device_id`: `pi-001`)
- Threshold warnings (normal / warning / critical)
- Basic trend + spike detection in Lambda
- Login / register (users stored in DynamoDB)
- Save thresholds from the web UI
- Optional SNS email alerts
- Manual test ingest form on the dashboard

## Tech Stack

- **Device:** Raspberry Pi + Sense HAT, or `sense_emu` emulator  
- **Cloud:** API Gateway, Lambda (Python), DynamoDB, SNS  
- **Dashboard:** Flask, Jinja2, Chart.js  
- **Region:** `ap-southeast-2` (see `.env.example`)

## Setup

### 1. Install locally

```bash
cd smart_env_monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure `.env`

`.env` is not in git. Copy the example and fill in your values:

```bash
cp .env.example .env
```

You need at least:

```
AWS_API_BASE_URL=https://YOUR_API_ID.execute-api.ap-southeast-2.amazonaws.com
DEVICE_API_KEY=your-key-here
DEVICE_ID=pi-001
```

`DEVICE_API_KEY` must match the key on the **ingest** Lambda in AWS.

### 3. Run everything (3 terminals)

**Terminal 1 — Emulator GUI**

```bash
source .venv/bin/activate
sense_emu_gui
# or: python3 -m sense_emu.gui
```

Set sliders to something realistic (~25°C, ~55% humidity, ~1013 hPa). Zero values get rejected.

**Terminal 2 — Device uploader**

```bash
source .venv/bin/activate
PYTHONPATH=. python3 device/emulator_uploader.py
# or: PYTHONPATH=. python3 device/device_sender.py
```

You want to see `HTTP 201` each time.

**Terminal 3 — Dashboard**

```bash
source .venv/bin/activate
PYTHONPATH=. python3 run.py
```

Open http://127.0.0.1:5001 → register → log in.

### AWS (already deployed for marking)

If you're only running the client side, you just need a working API URL and device key in `.env`.

To deploy yourself: create DynamoDB tables (`SensorData`, `DeviceSettings`, `Users`), zip Lambdas with the `shared/` folder, hook routes on HTTP API (**payload format 2.0**), set Lambda env vars. More detail in `docs/setup_guide.md` and `report/`.

## AWS Services Used

- API Gateway (HTTP API)
- Lambda — ingest, dashboard, settings, auth, health
- DynamoDB — readings, settings, users, alert cooldown
- SNS — email alerts (optional)
- CloudWatch — Lambda logs
- IAM — Lambda execution roles

## Demo / Usage

1. Start emulator + uploader + Flask (see above).  
2. Log in on the dashboard — readings should update within a few seconds.  
3. Move the **temperature** slider above your max threshold → warning banner goes orange/red, chart crosses the line.  
4. Try **Settings** at the bottom → change limits → Save to Cloud → reload page to confirm they stuck.  
5. Use **Simulate Sensor Reading** to push a fake value without touching the emulator.  
6. If SNS is set up, check your email after a breach (cooldown ~10 min per level).

Valid sensor ranges: temp -40–100°C, humidity 0–100%, pressure 800–1200 hPa.

## Common Issues

**HTTP 403 on upload** — `DEVICE_API_KEY` in `.env` doesn't match the ingest Lambda. Fix one side so they match.

**Dashboard empty but uploader shows 201** — Check `DEVICE_ID` is `pi-001` and `AWS_API_BASE_URL` is correct. Try:  
`curl -s "$AWS_API_BASE_URL/data?device_id=pi-001"`

**Emulator shows garbage (e.g. humidity 16172)** — Stale emulator. Run `pkill -f sense_emu`, restart GUI, set sliders, then restart uploader.

**404 on /settings** — Route missing on API Gateway. See `infrastructure/AWS_HTTP_API_SETTINGS_ROUTES.md`.

**ModuleNotFoundError: cloud** — Run from project root with `PYTHONPATH=.` (see commands above).

## Project layout (quick)

```
api/          Flask routes + pages
cloud/        API Gateway HTTP client
device/       Sensor upload scripts
lambda/       Lambda source (+ shared/)
templates/    Dashboard + login HTML
static/       JS + CSS
run.py        Start Flask
```

Warnings and analysis always come from the **get_dashboard_data** Lambda — not from Flask.
