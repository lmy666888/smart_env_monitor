# Smart Environment Cloud Monitor (AWS Brain)

**AWS is the system brain.** Sense HAT / emulator / Pi collectors send readings to API Gateway; Lambda writes **DynamoDB** and computes warnings, trends, and predictions; Flask is a thin **BFF + UI** (session cookie, proxy, local sensor worker).

```
Sense HAT / sense_emu / mock (dev)
        │ POST /ingest
        ▼
API Gateway  →  Lambda ingest_sensor_data  →  DynamoDB SensorData
                        │
                        ▼
              Lambda get_dashboard_data
              (warnings, analysis, settings)
                        │
        GET /data       │
        ▼               │
Flask /api/data (proxy) ┘  →  Browser dashboard (Chart.js)
        │
        └── CloudWatch monitors Lambda, API Gateway, DynamoDB
```

Flask **does not** recompute warnings, trends, or predictions when `USE_AWS_BRAIN=true` (default).

---

## Quick start

```bash
cd smart_env_monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit SECRET_KEY if needed
python run.py
```

1. Open **http://127.0.0.1:5001/login** — register via the form (calls `POST /register` → DynamoDB **Users**), then log in (`POST /login`).
2. Dashboard polls **`GET /api/data`** → AWS **`GET /data`** (authoritative payload).

For local UI-only demos: `export DISABLE_AUTH=1` (trusted networks only).

---

## Configuration (`config/cloud_config.py`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `USE_AWS_BRAIN` | `true` | Proxy AWS for data/settings/auth |
| `ENABLE_BACKGROUND_COLLECTOR` | `false` | Flask background ingest loop (off for cloud demo) |
| `AWS_API_BASE_URL` | class API URL | API Gateway base |
| `CLOUD_TIMEOUT_SECONDS` | `12` | HTTP client timeout |
| `LOCAL_FALLBACK_ON_AWS_ERROR` | `false` | Use local analysis + optional SQLite if AWS down |
| `USE_SQLITE_CACHE` | `false` | Mirror ingest locally (not primary) |
| `DEVICE_ID` | `pi-001` | DynamoDB partition key |

Endpoint paths: `/data`, `/ingest`, `/settings`, `/login`, `/register`, `/health`.

---

## API Gateway routes (production)

| Route | Method | Lambda | Role |
|-------|--------|--------|------|
| `/ingest` | POST | `ingest_sensor_data` | Validate & store readings |
| `/data` | GET | `get_dashboard_data` | Sensor history, settings, **warnings**, **analysis** |
| `/settings` | GET, POST | `settings_handler` | DeviceSettings thresholds |
| `/login` | POST | `auth_handler` | Users table authentication |
| `/register` | POST | `auth_handler` | Create user in Users |
| `/health` | GET | `health_check` | Liveness |

**Region:** `ap-southeast-2`  
**Base URL:** `https://9jzbd9a34j.execute-api.ap-southeast-2.amazonaws.com`

### Flask proxy routes

| Flask | Proxies AWS |
|-------|-------------|
| `GET /api/data` | `GET /data` |
| `POST /api/ingest` | `POST /ingest` |
| `GET/POST /api/settings` | `GET/POST /settings` |
| `POST /api/login` | `POST /login` |
| `POST /api/register` | `POST /register` |
| `GET /api/health` | `GET /health` |

Errors return `success: false`, `source: "aws"`, `error_code`, and `fallback_used: false` unless `LOCAL_FALLBACK_ON_AWS_ERROR` is enabled (`source: "local_fallback"`).

---

## DynamoDB tables

| Table | Key | Purpose |
|-------|-----|---------|
| **SensorData** | `device_id` + `timestamp` | All sensor readings (SoT) |
| **DeviceSettings** | `device_id` = `pi-001` (env `DEVICE_ID`) | Threshold min/max |
| **Users** | `username` | `email`, `password_hash` (Werkzeug) for login/register |

---

## Lambda responsibilities

| Function | Responsibility |
|----------|----------------|
| `ingest_sensor_data` | Ingest validation → SensorData |
| `get_dashboard_data` | Query SensorData + DeviceSettings; run **warnings_util** + **analysis_service** |
| `settings_handler` | Read/write DeviceSettings |
| `auth_handler` | Login/register against Users |
| `health_check` | Health JSON |

Reference code lives under `lambda/` (deploy as zip to AWS).

---

## CloudWatch

A CloudWatch dashboard in your AWS account should monitor:

- Lambda invocations / errors (`ingest_sensor_data`, `get_dashboard_data`, …)
- API Gateway 4xx/5xx and latency
- DynamoDB consumed capacity / throttles on SensorData, DeviceSettings, Users

---

## Raspberry Pi / Sense HAT emulator flow

1. **Read:** `sensor/reader.py` — `sense_emu` → `real_sense_hat` → per-cycle `mock` fallback.
2. **Upload:** `device/emulator_uploader.py` (recommended for demo) or Flask background collector / `device_sender`.
3. **View:** Browser → Flask `/api/data` → AWS `/data` (dashboard shows `sensor_backend` from cloud).

### Final cloud demonstration (recommended)

Use **system Python** for the emulator uploader (not the Flask venv) so invalid venv SenseEMU reads are not posted as mock data.

**Terminal 1 — Sense HAT Emulator GUI**

```bash
python3 -m sense_emu.gui
```

**Terminal 2 — Emulator → AWS ingest (`source=sense_emu`)**

```bash
cd ~/Desktop/smart_env_monitor
python3 device/emulator_uploader.py
```

**Terminal 3 — Flask dashboard (background collector off)**

```bash
cd ~/Desktop/smart_env_monitor
source .venv/bin/activate
ENABLE_BACKGROUND_COLLECTOR=false python run.py
```

**Browser:** http://127.0.0.1:5001

Verify in logs:

- Flask: `Background sensor collector disabled; dashboard will read cloud data only.`
- Uploader: `[POST] source=sense_emu …`
- Flask: `[DEBUG] /api/data returning sensor_backend=sense_emu`
- Dashboard **Sensor Backend:** `Sense HAT Emulator via AWS Cloud`

### Optional: Flask background collector

```bash
ENABLE_BACKGROUND_COLLECTOR=true python run.py
```

### Legacy device sender (project venv)

```bash
export DEVICE_ID=pi-001
python -m device.device_sender
```

---

## Test AWS endpoints with curl

```bash
BASE=https://9jzbd9a34j.execute-api.ap-southeast-2.amazonaws.com

curl -s "$BASE/health" | jq .

curl -s -X POST "$BASE/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo1","email":"demo1@example.com","password":"secret12"}' | jq .

curl -s -X POST "$BASE/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo1","password":"secret12"}' | jq .

curl -s -X POST "$BASE/ingest" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"pi-001","temperature":23.5,"humidity":55,"pressure":1013}' | jq .

curl -s "$BASE/data?device_id=pi-001" | jq .

curl -s "$BASE/settings" | jq .

curl -s -X POST "$BASE/settings" \
  -H "Content-Type: application/json" \
  -d '{"temp_min":0,"temp_max":40,"humidity_min":20,"humidity_max":80,"pressure_min":980,"pressure_max":1030}' | jq .
```

---

## Project layout

| Path | Role |
|------|------|
| `config/cloud_config.py` | AWS Brain URLs and flags |
| `cloud/client.py` | HTTP client for all API Gateway routes |
| `services/aws_proxy.py` | Pass-through `/data` + runtime metadata |
| `services/local_fallback.py` | Deprecated local analysis (optional offline) |
| `services/analysis_service.py` | **Fallback only** (Lambda copy in `lambda/shared/`) |
| `api/routes.py` | Thin Flask proxies |
| `api/auth.py` | Session after AWS login |
| `sensor/` | Reader, collector, upload worker |
| `lambda/` | Authoritative serverless reference |
| `legacy/` | SQLite cache, Sense HAT LED (optional) |

---

## Local development modes

| Mode | Env | Behaviour |
|------|-----|-----------|
| **Production (default)** | `USE_AWS_BRAIN=true` | All brain logic on AWS |
| **Auth bypass** | `DISABLE_AUTH=1` | Skip login (demos only) |
| **Offline fallback** | `LOCAL_FALLBACK_ON_AWS_ERROR=true` | Local warnings/analysis if AWS down |
| **SQLite mirror** | `USE_SQLITE_CACHE=1` | Optional local insert on ingest |
| **Mock sensor** | `USE_MOCK_SENSOR=1` | Random-walk data for testing |

---

## Security

- Passwords are verified in **AWS** (`auth_handler`); Flask stores only session state.
- Set a strong `SECRET_KEY` in `.env`.
- Do not commit `.env` or use `DISABLE_AUTH=1` in production.

---

## Assignment 2 note

SQLite is **not** the system of record. Warnings and analysis in production are produced by **`get_dashboard_data` Lambda**, not Flask `services/dashboard_service.py` (deprecated wrapper).
