# Troubleshooting

## Dashboard blank or error banner

- Confirm Flask is running (`python run.py`) and you open http://127.0.0.1:5001/dashboard.
- DevTools → Network → `/api/data`. A 5xx here usually means API Gateway or Lambda failed upstream.
- Check CloudWatch logs for `get_dashboard_data` and `ingest_sensor_data`.

## Readings show `--`

- `/data` may return empty `sensor_data`. Call your API Gateway `/data?device_id=pi-001` with curl.
- Run an uploader (`device/emulator_uploader.py`) and confirm a new row in DynamoDB.

## Cloud freshness or “Last device upload” wrong

- Both use `latest.timestamp` from `/data`. Hard-refresh the browser (cache).
- If timestamp is old, the emulator uploader may be stopped.

## Settings reset to 0 / 40 after save

- DeviceSettings partition key must be **`device_id`** (e.g. `pi-001`), not legacy `id=global`.
- Redeploy `settings_handler` and `get_dashboard_data` with current `lambda/shared/dynamo_settings.py`.
- Verify in DynamoDB Console and with `curl "$BASE/settings"`.

## Warnings when values look normal

- Thresholds in DynamoDB may be stricter than you expect. Relax via **Save to cloud** or POST `/settings`.

## Chart missing

- Chart.js loads from CDN in `templates/index.html` — needs network access.
- Confirm `<canvas id="tempChart">` is present.

## POST /settings returns Not Found

- API Gateway route missing. See `infrastructure/AWS_HTTP_API_SETTINGS_ROUTES.md`.

## Ingest fails

- Check `AWS_INGEST_URL` / base URL in `.env`.
- CloudWatch for `ingest_sensor_data` validation errors (humidity must be 0–100, etc.).

## Optional legacy pieces

- `USE_SQLITE_CACHE=1` writes to `legacy/database.py` SQLite — not the cloud source of truth.
- Sense HAT LED uses `legacy/display_service.py` and cached settings from cloud fetch.
