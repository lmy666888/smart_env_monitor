# Setup Guide

This guide explains how to run the Smart Environment Monitoring System
locally and how the pieces map to the deployed AWS resources.

## 1. Prerequisites

- Python 3.10+ (only needed if you want to run the legacy Flask app or the
  device-side script locally).
- A modern browser (Chrome, Edge, Firefox, Safari).
- (Optional) AWS account if you want to redeploy the Lambdas.

## 2. Project layout

```
smart_env_monitor/
├── frontend/            Static HTML/CSS/JS dashboard (talks directly to AWS).
├── lambda/              Source code for the AWS Lambda backends.
│   └── shared/          Shared analysis + warning helpers used by Lambdas
│                        (and by the legacy Flask app).
├── device/              Device-side scripts (run on the Raspberry Pi).
├── sensors/             Legacy emulator-based sensor reader (Flask path).
├── legacy/              Original Assignment 1 Flask app (kept for reference).
├── templates/, static/  Templates / assets used by the legacy Flask app.
├── docs/                Documentation (you are here).
└── config.py            Shared configuration class for Python components.
```

## 3. AWS endpoint

The frontend talks to:

```
https://9jzbd9a34j.execute-api.ap-southeast-2.amazonaws.com/data
```

This URL is set in `frontend/config.js`. Update `API_ENDPOINT` if the API
Gateway URL changes.

## 4. Running the frontend locally

The frontend is a fully static site, but most browsers block `fetch()` from
`file://` pages, so serve it over HTTP:

```bash
cd frontend
python3 -m http.server 8000
```

Then open <http://localhost:8000/login.html> in your browser and use the demo
credentials `admin / admin123`.

The dashboard will:

1. Fetch the AWS endpoint every few seconds.
2. Validate, sort and display the latest reading.
3. Render trend/spike analysis and a multi-series Chart.js graph.
4. Apply threshold checks using the `settings` block in the API response.

## 5. Running the legacy Flask app (optional)

The legacy SQLite-backed Flask app is kept under `legacy/` for reference:

```bash
pip install -r requirements.txt
python -m legacy.app
```

It serves the same dashboard on `http://localhost:5000` using local SQLite
data and the Sense HAT emulator.

## 6. Running the device sender on a Pi

```bash
export INGEST_ENDPOINT="https://<api-id>.execute-api.<region>.amazonaws.com/ingest"
export DEVICE_ID="pi-001"
export SEND_INTERVAL=30
python -m device.device_sender
```

## 7. Updating the Lambdas

Each file in `lambda/` is a self-contained handler. Zip the file plus
`lambda/shared/*` if needed and upload via the AWS console or your IaC tool.
Required environment variables are documented at the top of each handler.
