# Setup Guide

How to run the Smart Environment Monitor locally and connect it to your AWS API Gateway stack.

## Prerequisites

- Python 3.10 or newer
- Modern browser
- Deployed API Gateway + Lambda + DynamoDB (or use the course AWS account URL in `.env`)

## Layout

| Folder | Role |
|--------|------|
| `api/` | Flask app, `/api/*` routes, HTML pages |
| `cloud/` | HTTP client for API Gateway |
| `config/` | Environment and URL settings |
| `sensor/` | Sensor reader and optional background uploader |
| `device/` | Standalone ingest scripts (emulator, Pi) |
| `services/` | AWS proxy and optional local fallback |
| `lambda/` | Source to zip and deploy to AWS |
| `templates/`, `static/` | Dashboard UI |
| `legacy/` | Optional SQLite + Sense HAT LED |
| `run.py` | Start the Flask app |

## Environment

Copy `.env.example` to `.env`. Minimum for cloud mode:

- `AWS_API_BASE_URL` — API Gateway base (no trailing path)
- `SECRET_KEY` — Flask session secret
- `DEVICE_ID` — usually `pi-001`

Optional: `DISABLE_AUTH=1` for quick UI testing on a trusted machine.

## Run the dashboard

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Open http://127.0.0.1:5001/dashboard (port from `config/settings.py`).

The UI calls `/api/data`, which proxies AWS `GET /data`.

## Sense HAT Emulator + cloud ingest

1. `python3 -m sense_emu.gui`
2. In another terminal: `python3 device/emulator_uploader.py`
3. Flask: `ENABLE_BACKGROUND_COLLECTOR=false python run.py`

Use system Python for step 2 so sense_emu matches your OS install.

## Pi / alternate upload

```bash
export DEVICE_ID=pi-001
python -m device.device_sender
```

Requires `AWS_INGEST_URL` or `AWS_API_BASE_URL` in the environment (see `config`).

## Alternate Flask entry

```bash
python -m legacy.app
```

Same `create_app()` as `run.py`.

## Redeploy Lambdas

Zip each handler with `shared/` at the archive root. Set table names in Lambda environment variables to match your DynamoDB tables.
