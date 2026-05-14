# Setup Guide

How to run **SMART_ENV_MONITOR** locally and how it maps to AWS.

## 1. Prerequisites

- Python 3.10+ (Flask dashboard + optional device sender).
- A modern browser.
- (Optional) AWS account if you redeploy Lambdas or change API Gateway.

## 2. Project layout

```
smart_env_monitor/
├── api/                 Flask app factory, REST `/api/*`, HTML pages (`pages` blueprint)
├── cloud/               HTTP client for API Gateway
├── config/              Settings (`config.settings`)
├── sensor/              Sense HAT / emulator reads + cloud ingest collector
├── device/              Standalone Pi uploader (`python -m device.device_sender`)
├── services/            Dashboard payload, warnings, analysis
├── templates/, static/  Flask dashboard (canonical UI)
├── lambda/              Lambda source + `shared/` helpers for deploy zips
├── legacy/              SQLite cache + Sense HAT LED helpers (see `legacy/README.md`)
├── docs/                Documentation
├── run.py               Preferred local entrypoint
└── requirements.txt
```

## 3. AWS endpoints

Configure URLs via environment variables or `.env` (see `config/settings.py` and root `README.md`). Typical values include `AWS_DATA_URL`, `AWS_INGEST_URL`, and `AWS_SETTINGS_URL`.

## 4. Running the Flask dashboard (recommended)

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DISABLE_AUTH=1             # optional, for quick local demos
python run.py
```

Open **http://127.0.0.1:5001/dashboard** (default port in `config.settings`).

The browser loads data through Flask (`/api/data`), which proxies DynamoDB-backed API Gateway responses.

## 5. Alternate entrypoint

```bash
python -m legacy.app
```

Same application as `run.py` (`create_app()`).

## 6. Device sender on a Pi

```bash
pip install -r requirements.txt
export AWS_INGEST_URL="https://<api-id>.execute-api.<region>.amazonaws.com/ingest"
export DEVICE_ID="pi-001"
python -m device.device_sender
```

Use the same venv and `config` / `cloud` defaults as on the laptop when possible.
