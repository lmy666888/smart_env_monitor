# Test Plan

Manual checks for the Flask dashboard and AWS backend. Default URL: http://127.0.0.1:5001

## 1. Happy path

1. Run `python run.py` with valid `.env` AWS URLs.
2. Run `python3 device/emulator_uploader.py` (or ingest via curl).
3. Open dashboard, sign in if auth enabled.
4. **Expected:** `/api/data` 200, readings and chart update, freshness Live/Recent.

## 2. Threshold warnings

1. Lower `temp_max` (or other limits) via **Save to cloud**.
2. Wait for next poll.
3. **Expected:** warning level, list, and banner show violations.

## 3. Empty sensor data

1. Use an empty DynamoDB table or device with no rows.
2. **Expected:** empty state or placeholders; no JavaScript crash.

## 4. Invalid ingest

1. POST invalid JSON to `/ingest` (e.g. humidity 150).
2. **Expected:** 400 from Lambda; dashboard still shows previous valid data.

## 5. Network / AWS down

1. Set invalid `AWS_DATA_URL` or block network.
2. **Expected:** error UI; with `LOCAL_FALLBACK_ON_AWS_ERROR=true`, degraded local payload instead.

## 6. Spike detection

1. Ingest two readings where temperature jumps more than the spike threshold (default 3°C).
2. **Expected:** spike message in Temperature intelligence.

## 7. Chart edge case

1. Only one point in `sensor_data`.
2. **Expected:** chart renders a single point without error.

## 8. Lambda smoke (optional)

```bash
python lambda/health_check.py
python lambda/get_dashboard_data.py   # needs AWS credentials + tables
```

## 9. Settings round-trip

1. Save custom thresholds in the UI.
2. `curl` GET `/settings` and GET `/data` — **Expected:** same values in `settings` object.
