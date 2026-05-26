"""Device-side reading wrapper — adds timestamp to sensor reads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sensor.reader import get_sensor_source_name, read_from_emulator


def read_reading() -> Optional[Dict[str, Any]]:
    reading = read_from_emulator()
    if not reading:
        return None
    return {
        "temperature": reading["temperature"],
        "humidity": reading["humidity"],
        "pressure": reading["pressure"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def get_backend_name() -> str:
    return get_sensor_source_name()
