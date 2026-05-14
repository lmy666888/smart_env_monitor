"""
Standalone device uploader (Raspberry Pi or laptop with emulator).

POSTs each reading to API Gateway ingest using the shared ``CloudAPIClient``
(``requests`` + retries + timeouts).

Environment variables mirror ``config.settings`` (see README).

Run:
    python -m device.device_sender
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from cloud.client import CloudAPIClient
from config import get_config
from device.sensor_reader import get_backend_name, read_reading

logger = logging.getLogger("smart_env_monitor.device.sender")

SEND_INTERVAL = int(os.environ.get("SEND_INTERVAL", os.environ.get("SENSOR_INTERVAL", "5")))


def run_loop(max_iterations: Optional[int] = None) -> None:
    cfg = get_config()
    client = CloudAPIClient(cfg)
    device_id = getattr(cfg, "DEVICE_ID", "pi-001")
    interval = max(1, SEND_INTERVAL)

    logger.info(
        "Device sender started. backend=%s device_id=%s interval=%ss endpoint=%s",
        get_backend_name(),
        device_id,
        interval,
        getattr(cfg, "AWS_INGEST_URL", ""),
    )

    iteration = 0
    while True:
        reading = read_reading()
        if reading is None:
            logger.warning("Skipping cycle: no valid reading available.")
        else:
            payload = {
                "device_id": device_id,
                "temperature": reading["temperature"],
                "humidity": reading["humidity"],
                "pressure": reading["pressure"],
            }
            ts = reading.get("timestamp")
            if ts:
                payload["timestamp"] = ts
            ok = client.post_sensor_reading(payload)
            if ok:
                logger.info("Posted reading: %s", payload)
            else:
                logger.warning("Upload failed for reading: %s", payload)

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
