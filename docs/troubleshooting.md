# Troubleshooting

## Browser shows errors or blank dashboard

- Run the **Flask** app (`python run.py`) and open **http://127.0.0.1:5001/dashboard** — the UI is served from `templates/` + `static/`, not from a separate static tree.
- In DevTools → Network, inspect **`/api/data`** (Flask → AWS). Failures there mirror API Gateway / Lambda issues; check CloudWatch for the Lambdas behind `/data` and `/ingest`.

## Latest values stuck at `--`

- The `sensor_data` array in the AWS response might be empty. Inspect the JSON from `/api/data` (or call your API Gateway `/data` URL directly).
- Invalid readings are dropped server-side in Lambda ingest validation.

## Settings revert to 0 / 40 after “Save to cloud”

- **POST /settings returns 500 ValidationException:** DeviceSettings partition key must be **`device_id`** (e.g. `pi-001`), not legacy `id=global`. Redeploy `settings_handler` + `get_dashboard_data` with updated `shared/dynamo_settings.py`.
- **POST succeeded but GET /data still shows defaults:** ensure every Lambda uses `SETTINGS_TABLE_NAME=DeviceSettings` and the same `device_id` as `DEVICE_ID` / query param.
- Verify in DynamoDB Console → **DeviceSettings** → item `{ "device_id": "pi-001", "temp_min": ... }`.
- Test directly: `curl -s "$BASE/settings" | jq .` after saving.
- Redeploy `settings_handler` and `get_dashboard_data` zips including `shared/dynamo_settings.py`.

## Warning banner stays orange when readings look fine

- The `settings` block from DynamoDB might be too strict. Adjust thresholds via **Save to cloud** (Flask `/api/settings` → AWS `/settings`) or edit DynamoDB.

## Chart not rendering

- Confirm the Chart.js CDN URL in `templates/index.html` is reachable.
- The page must include `<canvas id="tempChart">` (see `templates/index.html`).

## Legacy / SQLite / Sense HAT

- Optional SQLite mirror: `USE_SQLITE_CACHE=1` uses `legacy/database.py`.
- LED matrix helpers: `legacy/display_service.py`. See `legacy/README.md`.

## Device sender cannot post readings

- Verify `AWS_INGEST_URL` is set (see `config/settings.py`; older docs may mention `INGEST_ENDPOINT`).
- Confirm the device has internet access.
- Check CloudWatch logs of `ingest_sensor_data` for 4xx validation errors.
