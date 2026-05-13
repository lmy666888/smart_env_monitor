# Troubleshooting

## Dashboard shows "Failed to load sensor data"

- Open the browser DevTools "Network" tab and inspect the request to the
  AWS endpoint.
  - **HTTP 4xx / 5xx**: the API Gateway / Lambda is broken; check the
    CloudWatch logs of `get_dashboard_data`.
  - **CORS error in the console**: ensure the API Gateway response
    includes `Access-Control-Allow-Origin: *` (the bundled Lambdas already
    do this).
  - **Network timeout**: confirm you have internet access; the request
    times out after `FETCH_TIMEOUT_MS` (8 s by default).

## Latest values stuck at `--`

- The `sensor_data` array might be empty. Check the raw response (DevTools
  → Network → click on `data` → "Preview").
- Readings that fail validation (`validateSensorReading`) are filtered out.
  Inspect the response for non-numeric or out-of-range values.

## Warning banner stays orange when readings look fine

- The `settings` block returned by the API might be too strict. The
  banner just compares the latest reading against `temp_min/max`,
  `humidity_min/max` and `pressure_min/max`.
- Update settings via the update Lambda (or DynamoDB directly) and
  refresh.

## Chart not rendering

- Confirm `https://cdn.jsdelivr.net/npm/chart.js@4.4.1/...` is reachable
  (or download it locally if you are offline).
- The chart requires the `<canvas id="tempChart">` element to exist on the
  page; do not remove it from `index.html`.

## Browser blocks `fetch()` from `file://`

- Serve the `frontend/` folder via `python3 -m http.server` (see the
  setup guide). Modern browsers reject cross-origin requests when the
  page is loaded from a local file.

## Legacy Flask app fails to import `services.analysis_service`

- The legacy app was originally part of Assignment 1 and predates the
  current `lambda/shared/` layout. The new system uses the AWS endpoint
  via the static frontend; you do not need to run the Flask app for the
  coursework demo. If you do want to run it, update the imports in
  `legacy/app.py` to point at `lambda/shared/`.

## Device sender cannot post readings

- Verify `INGEST_ENDPOINT` is set and points at the ingest Lambda URL.
- Confirm the device has internet access.
- Check CloudWatch logs of `ingest_sensor_data` for 4xx validation errors.
