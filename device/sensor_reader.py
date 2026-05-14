"""
Device-side reading wrapper (Pi / emulator).

Delegates to the shared ``sensor.reader`` implementation used by the Flask
collector, and adds an ISO timestamp field expected by standalone senders.
"""

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
    """Alias for logging / UI (matches historical device API)."""
    return get_sensor_source_name()
