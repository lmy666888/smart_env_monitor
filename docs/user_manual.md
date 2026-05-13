# User Manual

The Smart Environment Monitoring System dashboard shows real-time
temperature, humidity, and pressure readings collected by a Raspberry Pi
device and stored in AWS.

## 1. Logging in

1. Open `frontend/login.html` (or visit `/login.html` if hosted).
2. Enter the demo credentials: `admin / admin123`.
3. You will be redirected to the dashboard.

> The login screen is a **client-side gate only**, intended for coursework
> demonstration. It does not provide real authentication.

## 2. Dashboard sections

| Section | What it shows |
|---|---|
| System Status | "Online" / "Offline / Error" depending on the last API call. |
| Device ID | The `device_id` from the most recent reading. |
| Warning Count | Number of thresholds currently violated by the latest reading. |
| Last Successful Update | Local time of the last good fetch. |
| Warning Banner | Green for normal, orange for threshold warnings, red for connectivity / data errors. |
| Reading Cards | Latest temperature (°C), humidity (%) and pressure (hPa). |
| Warnings | One bullet per active threshold violation. |
| Dataset Info | How many readings the dashboard currently has loaded, plus earliest/latest timestamps. |
| Temperature Analysis | Spike/drop detection, overall trend direction, summary range. |
| Historical Chart | Line chart with three series: temperature, humidity, pressure. |
| Current Thresholds | The min/max values returned by the API in the `settings` block. |

## 3. Refresh cadence

By default the dashboard refetches every 5 seconds (see
`REFRESH_INTERVAL_MS` in `frontend/config.js`). Adjust as needed for the
demo or video recording.

## 4. Warning rules

Given the AWS `settings`, a warning is produced when the latest reading is:

- `temperature < temp_min` or `temperature > temp_max`
- `humidity < humidity_min` or `humidity > humidity_max`
- `pressure < pressure_min` or `pressure > pressure_max`

If none apply, the banner shows **"All readings are within normal ranges."**

## 5. Trend analysis

- **Spike / drop**: the difference between the two most recent temperature
  values; flagged if the change exceeds ±3 °C by default.
- **Trend**: the total change across all loaded readings; classified as
  "increasing", "decreasing" or "stable" using a ±0.5 °C delta.
- **Summary**: minimum / maximum temperature observed in the loaded window.

## 6. Error handling

- API errors and timeouts are shown on the warning banner and in the dataset
  info ("Last Fetch Status").
- If a previous refresh succeeded, that data is kept on screen while
  retrying so the dashboard does not blank out during transient failures.
