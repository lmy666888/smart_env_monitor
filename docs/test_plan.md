# Test Plan

The dashboard is the **Flask** app (`python run.py`). It polls **`/api/data`**, which proxies your API Gateway **`/data`** response. The following manual tests assume the stack is running locally (default **http://127.0.0.1:5001**).

## 1. Happy-path test

1. Run `python run.py` (use `export DISABLE_AUTH=1` if you want to skip login).
2. Open **http://127.0.0.1:5001/login**, sign in with `admin / admin123` when auth is enabled.
3. **Expected**: dashboard renders, `/api/data` returns 200 in DevTools, readings and chart populate.

## 2. Threshold warning test

1. Tighten thresholds via **Save to cloud** or call the AWS **`/settings`** Lambda with stricter values (e.g. lower `temp_max`).
2. Reload the dashboard.
3. **Expected**: warning banner and list reflect threshold violations for the latest cloud reading.

## 3. Empty `sensor_data` test

1. Temporarily clear the DynamoDB sensor table (or return an empty `sensor_data` from `/data`).
2. **Expected**: empty-state / placeholder readings, chart empty or minimal, no uncaught JS errors.

## 4. Malformed payload test

1. Ingest a reading that fails Lambda validation (e.g. non-numeric temperature).
2. **Expected**: row rejected at ingest; dashboard still renders prior valid cloud data.

## 5. Network failure test

1. Disable network or set a bogus `AWS_DATA_URL` in `.env`.
2. **Expected**: error handling in the UI, Flask logs show cloud fetch failures for `/data`.

## 6. Spike detection test

1. Push a reading that is `>3 °C` higher than the previous reading
   (using `simulate_sensor_data` Lambda with a different base temperature).
2. **Expected**: the "Spike / Drop Detection" box reports a spike with the
   delta value.

## 7. Chart edge cases

1. Trigger a refresh when only one valid reading is present.
2. **Expected**: the chart still renders without throwing an error and
   shows a single data point per series.

## 8. Lambda unit smoke

Each Lambda file can be executed directly for a quick local smoke test:

```bash
python lambda/health_check.py
python lambda/get_dashboard_data.py   # requires AWS creds + tables
```
