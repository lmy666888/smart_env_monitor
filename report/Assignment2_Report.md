# Smart Environment Cloud Monitor

## IoT / Cloud Computing Design Project — Assignment 2

**Course:** IoT and Cloud Computing  
**Platform:** AWS (Lambda, DynamoDB, API Gateway, SNS, CloudWatch)  
**Hardware:** Raspberry Pi + Sense HAT (emulator used for development)  
**Device ID:** `pi-001`  
**Date:** May 2026

---

## Table of Contents

1. Introduction  
2. Research and Design Decisions  
3. System Architecture  
4. Cloud Backend Implementation  
5. Dashboard and Device Implementation  
6. Security and Reliability  
7. Testing and Evaluation  
8. Challenges and Troubleshooting  
9. Deployment and User Guide  
10. Conclusion  
References

---

## 1. Introduction

Indoor environmental monitoring matters in places like server rooms, labs, and storage areas. Temperature, humidity, and pressure all need to stay within safe ranges — but basic data loggers only store readings locally. You still have to collect them manually, and there is no automatic alerting when something goes wrong.

This project builds a **cloud-connected environmental monitor** using a Raspberry Pi with a Sense HAT. The Pi reads temperature, humidity, and pressure, then sends data to AWS. A Flask web dashboard shows live readings, charts, threshold warnings, and trend analysis. When limits are exceeded, the system can send email alerts through SNS.

The important design choice: **the Pi only reads sensors and uploads data**. Everything else — storage, analysis, authentication, settings, and alerts — runs in AWS Lambda behind API Gateway. Flask acts as a thin proxy (BFF) and does not do the main processing itself. That matches the assignment requirement that backend services must be cloud-based.

**Objectives**

- Read environmental data from Sense HAT (or `sense_emu` emulator)  
- Ingest and store readings in DynamoDB via serverless Lambda  
- Show real-time dashboard with Chart.js and 4-second polling  
- Support login/registration stored in DynamoDB  
- Allow threshold configuration and SNS email alerts  
- Keep the edge device simple and the cloud backend scalable  

---

## 2. Research and Design Decisions

Before building, a few existing options were considered. Full enterprise stacks (AWS IoT Core + MQTT, Azure IoT Hub) add certificate management, brokers, and extra services that are overkill for a single-room monitor. Simpler platforms like ThingSpeak are easy to start with but limit custom logic, auth, and alerting.

For this project, a **serverless AWS stack** was the best fit: short bursts of work every few seconds, no need for a server running 24/7, and each part (ingest, dashboard, auth) can be a separate Lambda.

**Why serverless (Lambda)?**  
Sensor data arrives every ~5 seconds. Lambda only runs when a request comes in, so idle time costs nothing. Each function handles one job (ingest, dashboard, settings, auth).

**Why DynamoDB?**  
Readings are keyed by `device_id` + `timestamp` — a natural fit for time-series queries. No joins needed. On-demand mode avoids capacity planning.

**Why HTTP instead of MQTT?**  
MQTT would need AWS IoT Core or a broker. Here, `POST /ingest` to API Gateway is enough. The device gets a clear **HTTP 201** when data is actually saved. At one reading every 5 seconds, HTTP overhead is not a problem. MQTT would matter more at large scale or for two-way device control.

**Why SNS?**  
One `sns.publish()` call sends email to subscribed addresses. No SMTP setup. Easy to extend later (SMS, etc.).

**Why cloud at all?**  
The Pi cannot reliably host a database, serve multiple users, or send durable alerts. Once data is in DynamoDB, it survives Pi failures and can be viewed from anywhere.

---

## 3. System Architecture

### 3.1 End-to-end data flow

```
Sense HAT / sense_emu
    → device_sender.py (or emulator_uploader.py)
    → API Gateway  POST /ingest
    → Lambda ingest_sensor_data
    → DynamoDB SensorData

Browser
    → Flask BFF  GET /api/data
    → API Gateway  GET /data
    → Lambda get_dashboard_data
    → DynamoDB (readings + settings) + analysis + optional SNS
    → JSON back to dashboard (Chart.js)
```

Device ID used throughout: **`pi-001`**.

[INSERT DIAGRAM: End-to-end AWS architecture — Raspberry Pi → API Gateway → Lambda functions → DynamoDB tables, with SNS branch and Flask/browser on the left]

*Figure 1: End-to-end cloud architecture*

[INSERT DIAGRAM: Three-layer block diagram — Device (Pi + Sense HAT), Cloud (API Gateway, Lambdas, DynamoDB, SNS), Presentation (Flask + browser)]

*Figure 2: System layers and main data paths*

[INSERT DIAGRAM: Sequence diagram — ingestion flow and dashboard GET /data flow]

*Figure 3: Request sequence for ingest and dashboard retrieval*

### 3.2 Hardware

Raspberry Pi with Sense HAT (temperature, humidity, pressure on one board). Development used **`sense_emu`** GUI sliders instead of physical hardware. Accepted ranges everywhere in the stack: temperature -40–100°C, humidity 0–100%, pressure 800–1200 hPa.

### 3.3 AWS components

| Service | Role |
|---------|------|
| API Gateway HTTP API v2 | Routes: `/ingest`, `/data`, `/settings`, `/login`, `/register`, `/health` |
| Lambda (6 functions) | Ingest, dashboard, settings, auth, health, simulate |
| DynamoDB (4 tables) | SensorData, DeviceSettings, Users, AlertState |
| SNS | Email alerts on threshold breach |
| CloudWatch | Lambda logs and debugging |
| IAM | Per-function least-privilege roles |

Region used: **ap-southeast-2** (from project `.env.example`).

---

## 4. Cloud Backend Implementation

### 4.1 Data ingestion

`POST /ingest` → `ingest_sensor_data` Lambda.

- Checks **`X-DEVICE-KEY`** against `DEVICE_API_KEY` env var  
- Validates sensor ranges again server-side  
- Writes to **SensorData**: partition key `device_id`, sort key `timestamp` (ISO 8601)  
- Returns **HTTP 201** on success  

```python
table.put_item(Item={
    "device_id": body["device_id"],
    "timestamp": body.get("timestamp", datetime.now(timezone.utc).isoformat()),
    "temperature": Decimal(str(round(body["temperature"], 2))),
    "humidity": Decimal(str(round(body["humidity"], 2))),
    "pressure": Decimal(str(round(body["pressure"], 2))),
    "source": body.get("source", "unknown")
})
```

[INSERT SCREENSHOT: Lambda console — ingest_sensor_data environment variables (SENSOR_TABLE_NAME, DEVICE_API_KEY redacted)]

*Figure 4: Ingest Lambda configuration*

[INSERT SCREENSHOT: Terminal — device uploader showing HTTP 201 lines with T/H/P values]

*Figure 5: Successful cloud uploads from device*

### 4.2 Storage (DynamoDB)

| Table | Key | Purpose |
|-------|-----|---------|
| SensorData | device_id + timestamp | Time-series readings |
| DeviceSettings | device_id | Min/max thresholds (T, H, P) |
| Users | username | Login credentials (hashed passwords) |
| AlertState | alert_key | SNS cooldown (`pi-001:warning`, etc.) |

Dashboard Lambda queries last **50 readings** with `ScanIndexForward=False`.

[INSERT SCREENSHOT: DynamoDB SensorData table — items for pi-001 with temperature, humidity, pressure]

*Figure 6: Stored sensor readings in DynamoDB*

[INSERT SCREENSHOT: DynamoDB — list of all four tables]

*Figure 7: DynamoDB tables used by the project*

### 4.3 Processing and analytics (`get_dashboard_data`)

On each `GET /data`, the dashboard Lambda:

1. Loads recent readings and settings from DynamoDB  
2. **Warnings** — compares latest reading to thresholds; levels: normal / warning / critical  
3. **Analysis** (`lambda/shared/analysis_service.py`) — spike detection (~3°C jump), trend (stable/rising/falling/volatile), simple threshold prediction  
4. **SNS** — if warning or critical, `maybe_send_warning_alert()` with **10-minute cooldown** per device+level  

```python
def maybe_send_warning_alert(device_id, warning_status, latest_reading):
    if warning_status["level"] not in ("warning", "critical"):
        return
    alert_key = f"{device_id}:{warning_status['level']}"
    if _is_in_cooldown(alert_key):
        return
    sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=body)
```

[INSERT SCREENSHOT: CloudWatch Logs — get_dashboard_data execution showing query + warnings]

*Figure 8: Lambda processing visible in CloudWatch*

[INSERT SCREENSHOT: Email inbox — SNS alert e.g. [CRITICAL] Env alert — pi-001]

*Figure 9: SNS email alert after threshold breach*

[INSERT SCREENSHOT: SNS console — topic with confirmed email subscription]

*Figure 10: SNS topic setup*

### 4.4 Other Lambda routes

| Route | Lambda | Notes |
|-------|--------|-------|
| GET/POST /settings | settings_handler | Save/load thresholds; field alias normalisation |
| POST /login, /register | auth_handler | Users table + Werkzeug password hash |
| GET /health | health_check | Liveness check |

Settings and auth are fully cloud-backed — not stored only on the Pi.

Login example (cloud path):

```python
# auth_handler Lambda — password check against Users table
if not check_password_hash(stored_hash, provided_password):
    return {"statusCode": 401, "body": json.dumps({"error": "Invalid credentials"})}
```

### 4.5 Flask BFF

Flask proxies `/api/*` to API Gateway. Session cookies for login. Module `cloud_brain.py` raises an error if local analysis is attempted — **all analysis stays in Lambda**.

`CloudAPIClient` retries on 429/5xx and keeps **last successful payload** if AWS is down (shows “Stale” freshness).

---

## 5. Dashboard and Device Implementation

### 5.1 Web dashboard

- **Stack:** Jinja2 templates, vanilla JS (~870 lines), Chart.js, CSS grid layout  
- **Polls** `GET /api/data` every **4 seconds** (sensor sends every ~5s)  
- **UI:** status pills, reading cards, warning banner (green/orange/red), temperature chart with min/max threshold lines, analysis panel, settings form, manual ingest form  

[INSERT SCREENSHOT: Full dashboard — normal state, green banner, chart with threshold lines]

*Figure 11: Dashboard during normal operation*

[INSERT SCREENSHOT: Dashboard — warning/critical state, red/orange banner, value over threshold on chart]

*Figure 12: Dashboard during threshold breach*

[INSERT SCREENSHOT: Settings form + manual ingest form]

*Figure 13: Interactive controls*

[INSERT SCREENSHOT: Login and registration page]

*Figure 14: Authentication UI*

### 5.2 Device software

`device/device_sender.py` or `device/emulator_uploader.py`:

- Read Sense HAT / `sense_emu`  
- Skip invalid readings (e.g. humidity 16172, pressure 0 from stale emulator)  
- POST JSON to `/ingest` with `X-DEVICE-KEY`  
- Uses `urllib.request` to keep dependencies light on the Pi  

[INSERT SCREENSHOT: sense_emu GUI + terminal with HTTP 201 output side by side]

*Figure 15: Emulator and uploader running together*

### 5.3 Running the demo (three terminals)

**Terminal 1 — Flask**
```bash
source .venv/bin/activate
python run.py
```

**Terminal 2 — Uploader**
```bash
source .venv/bin/activate
PYTHONPATH=. python device/device_sender.py
```

**Terminal 3 — Emulator (Pi with display)**
```bash
export DISPLAY=:0
/usr/bin/python3 -m sense_emu.gui
```

Set sliders to ~25°C, ~55% humidity, ~1013 hPa. Open `http://127.0.0.1:5001`, register, log in. Push temperature above max threshold to trigger warnings and SNS.

[INSERT SCREENSHOT: Three terminals — Flask, device_sender, emulator GUI]

*Figure 16: Live demo setup on Raspberry Pi*

---

## 6. Security and Reliability

**Transport:** All AWS calls use HTTPS. API Gateway enforces TLS.

**Device auth:** Shared secret in `X-DEVICE-KEY` header; stored in Lambda env and local `.env` (not in git).

**User auth:** Passwords hashed with Werkzeug before storage in DynamoDB. Flask session cookies: HttpOnly, SameSite=Lax, 8-hour lifetime. Login/register go through `auth_handler` Lambda.

**IAM:** Each Lambda role only gets the DynamoDB/SNS actions it needs (e.g. ingest → PutItem on SensorData only).

**Encryption:** DynamoDB encrypts at rest by default (AWS-managed keys).

**Monitoring:** CloudWatch Logs for every Lambda invocation. During development this was the main tool for fixing 502 errors, missing `dynamodb:Query` permissions, and null request bodies from wrong API Gateway payload version.

[INSERT SCREENSHOT: IAM role policy — scoped DynamoDB permissions]

*Figure 17: Least-privilege IAM for Lambda*

[INSERT SCREENSHOT: CloudWatch log stream — START/END/REPORT lines]

*Figure 18: CloudWatch monitoring*

**Reliability:** DynamoDB replicates across AZs. Lambda scales automatically. Dashboard degrades gracefully if cloud is unreachable. SNS retries email delivery.

**Cloud integration benefits:** Running the backend on AWS means the Pi can stay simple — no database daemon, no email server, no user account store on SD card. Lambda and DynamoDB scale with load: one `pi-001` device or ten more IDs only change traffic, not architecture. When nothing is uploading, compute cost drops to near zero. CloudWatch gives a single place to debug ingest, dashboard, and SNS issues without SSHing into production servers. For a university prototype this is enough; for deployment in a real facility the same pattern applies with minimal changes.

---

## 7. Testing and Evaluation

Manual tests covered the full pipeline (see `docs/test_plan.md`). All nine scenarios passed.

| # | Test | Result |
|---|------|--------|
| 1 | Ingest → DynamoDB → dashboard | Pass |
| 2 | Threshold warning on dashboard | Pass |
| 3 | Empty DB message | Pass |
| 4 | Invalid payload rejected (400) | Pass |
| 5 | Cloud down → stale data shown | Pass |
| 6 | Spike detection | Pass |
| 7 | Chart + threshold lines | Pass |
| 8 | GET /health | Pass |
| 9 | Settings save and reload from cloud | Pass |

**Demo flow:** Start Flask + uploader + emulator → confirm HTTP 201 → check DynamoDB items for `pi-001` → move emulator slider past threshold → banner turns orange/red → check CloudWatch → confirm SNS email (if configured) → save new thresholds and reload page.

[INSERT TESTING EVIDENCE: Dashboard with active warning after manual or emulator breach]

*Figure 19: Threshold warning test*

[INSERT TESTING EVIDENCE: CloudWatch log for successful ingest or dashboard run]

*Figure 20: CloudWatch test evidence*

[INSERT TESTING EVIDENCE: DynamoDB items for pi-001]

*Figure 21: Cloud storage verification*

SNS cooldown worked: repeated polls did not flood email; escalation to critical could still send a new alert.

---

## 8. Challenges and Troubleshooting

Real issues hit during development — short notes below.

**Sense emulator bad values**  
Sometimes humidity showed **16172** or pressure **0** (“Humidity Init Failed”, stale GUI). Fix: kill emulator processes, restart GUI, set sliders to valid values, then start uploader. Device-side range checks skip bad readings before upload.

**API Gateway 502**  
Integration used payload format **1.0** but Lambdas expect **2.0** → empty body, Lambda crash, 502. Fix: set integration to **2.0**. CloudWatch showed `null` body.

**Missing /settings route**  
Frontend got 404 on settings. Fix: add GET/POST `/settings` routes (CloudFormation in `infrastructure/httpapi-settings-routes.yaml`).

**DynamoDB permissions**  
Dashboard empty despite ingest working. Lambda role lacked **`dynamodb:Query`** on SensorData. CloudWatch showed `AccessDeniedException`. Fix: update IAM policy.

**Settings field names**  
Frontend sent `temperature_min`; DynamoDB expected `temp_min`. Saves looked OK but reload failed. Fix: alias normalisation in `dynamo_settings.py` and `settings_normalize.py`.

**SNS email not arriving**  
Usually unconfirmed subscription or wrong `SNS_TOPIC_ARN` on dashboard Lambda. Check spam folder for AWS confirmation link.

**Dependencies**  
Mixed `urllib3` / `sense-emu` versions broke the venv. Fix: delete `.venv`, reinstall from pinned `requirements.txt`.

**Quick checks**
```bash
# Test ingest
curl -X POST "$AWS_API_BASE_URL/ingest" \
  -H "Content-Type: application/json" \
  -H "X-DEVICE-KEY: $DEVICE_API_KEY" \
  -d '{"device_id":"pi-001","temperature":25,"humidity":55,"pressure":1013,"source":"test"}'

# Test data
curl -s "$AWS_API_BASE_URL/data?device_id=pi-001" | python3 -m json.tool
```

---

## 9. Deployment and User Guide

### 9.1 AWS setup (summary)

1. Create DynamoDB tables: SensorData (`device_id`, `timestamp`), DeviceSettings, Users, AlertState — on-demand billing.  
2. Package Lambdas: `zip -r ingest.zip ingest_sensor_data.py shared/` (repeat for dashboard, settings, auth, health). Upload Python 3.12, 128MB, timeout 15s on dashboard Lambda.  
3. API Gateway HTTP API — routes: POST `/ingest`, GET `/data`, GET+POST `/settings`, POST `/login`, POST `/register`, GET `/health`. Integration: **AWS_PROXY, payload format 2.0**.  
4. SNS topic → email subscription → confirm link → set `SNS_TOPIC_ARN` on dashboard Lambda.  
5. `.env`: `AWS_API_BASE_URL`, `DEVICE_API_KEY` (must match ingest Lambda), `DEVICE_ID=pi-001`.

[INSERT SCREENSHOT: API Gateway console — routes list mapped to Lambda functions]

*Figure 23: API Gateway route configuration*

### 9.2 Local setup

```bash
cd smart_env_monitor
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set AWS_API_BASE_URL, DEVICE_API_KEY, DEVICE_ID=pi-001
```

### 9.3 Using the dashboard

1. Open `http://127.0.0.1:5001` and register/login.  
2. Watch live T/H/P cards and chart (refreshes ~4s).  
3. **Freshness:** Live (&lt;15s), Recent (&lt;60s), Stale (older).  
4. **Settings:** change min/max → “Save to Cloud” → persists in DynamoDB.  
5. **Manual ingest:** submit test values to trigger warnings without moving emulator.  
6. **Alerts:** banner colour + optional SNS email (10 min cooldown per level).

[INSERT SCREENSHOT: Annotated dashboard — numbered callouts for status grid, banner, cards, chart, settings, ingest]

*Figure 22: Dashboard user guide (annotated)*

---

## 10. Conclusion

The Smart Environment Cloud Monitor shows a practical IoT + cloud pipeline: Pi reads sensors, AWS stores and processes data, Flask and Chart.js present it to users. Serverless components (Lambda, DynamoDB, API Gateway, SNS) keep the backend scalable and maintainable without running a dedicated server.

Main outcomes: working ingest with device key auth, cloud-side warnings and analytics, real-time dashboard, DynamoDB-backed settings and users, and optional SNS alerts. Development issues (emulator glitches, API Gateway config, IAM, field naming) were resolved using CloudWatch and systematic testing.

**Future work:** MQTT via IoT Core for many devices, WebSockets for faster UI updates, data retention/TTL for old readings, stronger anomaly detection.

**Real-world use:** Same pattern fits server rooms, greenhouses, or storage monitoring — one architecture from one sensor to many, with cloud handling the heavy work.

---

## References

1. AWS Lambda Developer Guide — https://docs.aws.amazon.com/lambda/  
2. Amazon DynamoDB Developer Guide — https://docs.aws.amazon.com/amazondynamodb/  
3. Amazon API Gateway Developer Guide — https://docs.aws.amazon.com/apigateway/  
4. Raspberry Pi Sense HAT documentation — https://www.raspberrypi.com/documentation/accessories/sense-hat.html  
5. Flask Documentation — https://flask.palletsprojects.com/  
6. Chart.js Documentation — https://www.chartjs.org/docs/

---

*End of Report*
