#!/usr/bin/env python3
"""
MacBook / demo mock cloud uploader.

Generates realistic indoor sensor values and POSTs to AWS /ingest with
source=mock_demo (never labelled as Sense HAT Emulator).

Requires explicit demo flags when used from automation:
    DEMO_MODE=true
    MOCK_UPLOAD_ENABLED=true

Run:
    DEMO_MODE=true MOCK_UPLOAD_ENABLED=true python3 device/mock_uploader.py
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Tuple

DEFAULT_API_URL = (
    "https://9jzbd9a34j.execute-api.ap-southeast-2.amazonaws.com/ingest"
)
DEFAULT_DEVICE_ID = "pi-001"
DEFAULT_INTERVAL = 5
SOURCE_LABEL = "mock_demo"


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_ingest_url() -> str:
    explicit = os.environ.get("AWS_INGEST_URL", "").strip()
    if explicit:
        return explicit
    base = os.environ.get(
        "AWS_API_BASE_URL",
        "https://9jzbd9a34j.execute-api.ap-southeast-2.amazonaws.com",
    ).rstrip("/")
    return f"{base}/ingest"


def _next_reading() -> Dict[str, float]:
    """Smooth random-walk within realistic indoor ranges."""
    state = getattr(_next_reading, "_state", None)
    if state is None:
        state = {"temperature": 22.0, "humidity": 55.0, "pressure": 1013.0}
        _next_reading._state = state  # type: ignore[attr-defined]

    state["temperature"] = max(15.0, min(32.0, state["temperature"] + random.uniform(-0.4, 0.4)))
    state["humidity"] = max(25.0, min(75.0, state["humidity"] + random.uniform(-1.5, 1.5)))
    state["pressure"] = max(990.0, min(1030.0, state["pressure"] + random.uniform(-0.5, 0.5)))

    return {
        "temperature": round(state["temperature"], 2),
        "humidity": round(state["humidity"], 2),
        "pressure": round(state["pressure"], 2),
    }


def _post_ingest(url: str, payload: Dict[str, Any]) -> Tuple[int, str]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
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
    if not (_env_flag("DEMO_MODE") and _env_flag("MOCK_UPLOAD_ENABLED")):
        print(
            "[ERROR] Mock uploader requires DEMO_MODE=true and MOCK_UPLOAD_ENABLED=true",
            file=sys.stderr,
        )
        sys.exit(1)

    ingest_url = _resolve_ingest_url()
    device_id = os.environ.get("DEVICE_ID", DEFAULT_DEVICE_ID).strip() or DEFAULT_DEVICE_ID
    interval = max(1, int(os.environ.get("UPLOAD_INTERVAL", str(DEFAULT_INTERVAL))))

    print("Mock demo → AWS ingest (NOT Sense HAT Emulator)")
    print(f"  ingest URL : {ingest_url}")
    print(f"  device_id  : {device_id}")
    print(f"  source     : {SOURCE_LABEL}")
    print(f"  interval   : {interval}s\n")

    while True:
        reading = _next_reading()
        payload = {
            "device_id": device_id,
            "source": SOURCE_LABEL,
            **reading,
        }
        status, body = _post_ingest(ingest_url, payload)
        if 200 <= status < 300:
            print(
                f"Mock cloud upload success source={SOURCE_LABEL} "
                f"T={reading['temperature']}°C H={reading['humidity']}% "
                f"P={reading['pressure']} hPa HTTP {status}"
            )
        else:
            print(
                f"Mock cloud upload failed source={SOURCE_LABEL} HTTP {status} {body[:300]}"
            )
        time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nMock uploader stopped.")
