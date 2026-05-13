# Test Plan

The system is exercised through the deployed AWS endpoint and a local
static frontend. The following manual tests cover the assignment
requirements.

## 1. Happy-path test

1. Run `python3 -m http.server 8000` in `frontend/`.
2. Open <http://localhost:8000/login.html>, log in with `admin / admin123`.
3. **Expected**: dashboard renders within ~2 seconds, "System Status"
   shows *Online*, "Last Fetch Status" shows *OK*, and the temperature,
   humidity and pressure cards all contain numeric values.

## 2. Threshold warning test

1. Edit `lambda/update_settings.py` invocation or call the settings
   Lambda with stricter thresholds (e.g. `temp_max = 20`).
2. Reload the dashboard.
3. **Expected**: the warning banner turns orange, the warning list
   contains a "Temperature too high" line and the warning count is
   non-zero.

## 3. Empty `sensor_data` test

1. Temporarily clear the DynamoDB sensor table (or call an endpoint that
   returns an empty `sensor_data` array).
2. **Expected**: the banner shows "No sensor readings available from the
   API.", every reading card shows `--`, the chart stays empty.

## 4. Malformed payload test

1. Manually return a reading with `"temperature": "n/a"` in a mock
   response.
2. **Expected**: the invalid reading is filtered out by
   `validateSensorReading`; remaining valid readings still render.

## 5. Network failure test

1. Disable network or change `API_ENDPOINT` to a bogus URL.
2. **Expected**: banner turns red with the underlying error message,
   "System Status" shows *Offline / Error*, but any previously displayed
   data remains on-screen.

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
