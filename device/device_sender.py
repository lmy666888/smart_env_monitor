"""
Device-side uploader.

Periodically reads a sensor reading via device.sensor_reader and POSTs it to
the AWS ingest endpoint.

Configuration via environment variables:
    INGEST_ENDPOINT   Full URL of the ingest API (e.g.
                      https://<id>.execute-api.<region>.amazonaws.com/ingest)
    DEVICE_ID         Unique identifier for this device (default: pi-001)
    SEND_INTERVAL     Seconds between successive readings (default: 30)
    SEND_TIMEOUT      HTTP request timeout seconds (default: 10)

Run on a Pi (or any machine):
    python -m device.device_sender
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Optional

from device.sensor_reader import get_backend_name, read_reading

logger = logging.getLogger("smart_env_monitor.device.sender")

INGEST_ENDPOINT = os.environ.get(
    "INGEST_ENDPOINT",
    # No default ingest URL is hard-coded: set this in the environment.
    "",
)
DEVICE_ID = os.environ.get("DEVICE_ID", "pi-001")
SEND_INTERVAL = int(os.environ.get("SEND_INTERVAL", "30"))
SEND_TIMEOUT = int(os.environ.get("SEND_TIMEOUT", "10"))


def post_reading(reading: dict) -> bool:
    """POST a single reading to the ingest endpoint. Returns True on success."""
    if not INGEST_ENDPOINT:
        logger.error("INGEST_ENDPOINT is not configured; cannot send reading.")
        return False

    body = json.dumps({"device_id": DEVICE_ID, **reading}).encode("utf-8")
    request = urllib.request.Request(
        INGEST_ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=SEND_TIMEOUT) as response:
            status = response.status
            if 200 <= status < 300:
                logger.info("Posted reading (HTTP %s): %s", status, reading)
                return True
            logger.warning("Unexpected response HTTP %s", status)
            return False
    except urllib.error.HTTPError as exc:
        logger.error("HTTP error %s while posting reading: %s", exc.code, exc.reason)
    except urllib.error.URLError as exc:
        logger.error("Network error while posting reading: %s", exc.reason)
    except Exception as exc:  # last-resort guard so the loop keeps running
        logger.exception("Unexpected error posting reading: %s", exc)
    return False


def run_loop(max_iterations: Optional[int] = None) -> None:
    """Read & send in a loop until interrupted (or max_iterations reached)."""
    interval = max(1, SEND_INTERVAL)
    logger.info(
        "Device sender started. backend=%s device_id=%s interval=%ss",
        get_backend_name(),
        DEVICE_ID,
        interval,
    )

    iteration = 0
    while True:
        reading = read_reading()
        if reading is None:
            logger.warning("Skipping cycle: no valid reading available.")
        else:
            post_reading(reading)

        iteration += 1
        if max_iterations is not None and iteration >= max_iterations:
            logger.info("Stopping after %s iterations.", iteration)
            return

        time.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        run_loop()
    except KeyboardInterrupt:
        logger.info("Device sender stopped by user.")
