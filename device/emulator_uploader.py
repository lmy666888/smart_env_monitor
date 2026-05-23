#!/usr/bin/env python3
"""Post sense_emu readings to API Gateway /ingest (use system Python, not Flask venv)."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

# --- Defaults (override via env) ---
DEFAULT_API_URL = (
    "https://9jzbd9a34j.execute-api.ap-southeast-2.amazonaws.com/ingest"
)
DEFAULT_DEVICE_ID = "pi-001"
DEFAULT_INTERVAL = 5
SOURCE_LABEL = "sense_emu"

TEMP_MIN, TEMP_MAX = -40.0, 80.0
HUMIDITY_MIN, HUMIDITY_MAX = 0.0, 100.0
PRESSURE_MIN, PRESSURE_MAX = 800.0, 1200.0


def _resolve_ingest_url() -> str:
    explicit = os.environ.get("AWS_INGEST_URL", "").strip()
    if explicit:
        return explicit
    base = os.environ.get(
        "AWS_API_BASE_URL",
        "https://9jzbd9a34j.execute-api.ap-southeast-2.amazonaws.com",
    ).rstrip("/")
    return f"{base}/ingest"


def _validate_reading(temperature: float, humidity: float, pressure: float) -> bool:
    if not (TEMP_MIN <= temperature <= TEMP_MAX):
        return False
    if not (HUMIDITY_MIN <= humidity <= HUMIDITY_MAX):
        return False
    if not (PRESSURE_MIN <= pressure <= PRESSURE_MAX):
        return False
    return True


def _read_emulator() -> Optional[Tuple[float, float, float]]:
    try:
        from sense_emu import SenseHat  # type: ignore
    except ImportError as exc:
        print(f"[ERROR] sense_emu not available: {exc}", file=sys.stderr)
        print("Start the emulator GUI first: python3 -m sense_emu.gui", file=sys.stderr)
        return None

    sense = SenseHat()
    try:
        temperature = float(sense.get_temperature())
        humidity = float(sense.get_humidity())
        pressure = float(sense.get_pressure())
    except Exception as exc:
        print(f"[SKIP] Emulator read failed: {exc}")
        return None

    if not _validate_reading(temperature, humidity, pressure):
        print(
            f"[SKIP] Invalid emulator values "
            f"T={temperature} H={humidity} P={pressure} "
            f"(expected T∈[{TEMP_MIN},{TEMP_MAX}], "
            f"H∈[{HUMIDITY_MIN},{HUMIDITY_MAX}], "
            f"P∈[{PRESSURE_MIN},{PRESSURE_MAX}])"
        )
        return None

    return temperature, humidity, pressure


def _ingest_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("DEVICE_API_KEY", "").strip()
    if key:
        headers["X-DEVICE-KEY"] = key
    return headers


def _post_ingest(url: str, payload: Dict[str, Any]) -> Tuple[int, str]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers=_ingest_headers(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return 0, str(exc.reason)


def main() -> None:
    ingest_url = _resolve_ingest_url()
    device_id = os.environ.get("DEVICE_ID", DEFAULT_DEVICE_ID).strip() or DEFAULT_DEVICE_ID
    interval = max(1, int(os.environ.get("UPLOAD_INTERVAL", str(DEFAULT_INTERVAL))))

    print("Sense HAT Emulator → AWS ingest uploader")
    print(f"  ingest URL : {ingest_url}")
    print(f"  device_id  : {device_id}")
    print(f"  source     : {SOURCE_LABEL}")
    print(f"  interval   : {interval}s")
    print("Press Ctrl+C to stop.\n")

    while True:
        values = _read_emulator()
        if values is None:
            time.sleep(interval)
            continue

        temperature, humidity, pressure = values
        payload = {
            "device_id": device_id,
            "source": SOURCE_LABEL,
            "temperature": round(temperature, 2),
            "humidity": round(humidity, 2),
            "pressure": round(pressure, 2),
        }

        status, response_body = _post_ingest(ingest_url, payload)
        print(
            f"[POST] source={SOURCE_LABEL} "
            f"T={payload['temperature']}°C "
            f"H={payload['humidity']}% "
            f"P={payload['pressure']} hPa "
            f"→ HTTP {status}"
        )
        if response_body:
            print(f"       response: {response_body[:500]}")

        time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nEmulator uploader stopped.")
