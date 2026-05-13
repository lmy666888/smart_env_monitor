"""
Device-side sensor reader.

Runs on the Raspberry Pi (or sense_emu desktop emulator) and produces
single normalised dict readings of the form:

    {
        "temperature": 26.5,
        "humidity": 62.0,
        "pressure": 1011.0,
        "timestamp": "2026-05-13T15:50:42.803254"
    }

Usage:
    from device.sensor_reader import read_reading
    reading = read_reading()

If neither the physical Sense HAT nor the emulator is available, the module
falls back to a software simulator so the demo can keep running.
"""

import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("smart_env_monitor.device.sensor")

# Try sense_emu first (works on a developer laptop), then sense_hat (real Pi),
# then fall back to a software simulator.
SenseHat: Optional[Any] = None
SENSOR_BACKEND = "simulator"

try:
    from sense_emu import SenseHat as _SenseEmu  # type: ignore
    SenseHat = _SenseEmu
    SENSOR_BACKEND = "sense_emu"
except ImportError:
    try:
        from sense_hat import SenseHat as _SenseHat  # type: ignore
        SenseHat = _SenseHat
        SENSOR_BACKEND = "sense_hat"
    except ImportError:
        SenseHat = None
        SENSOR_BACKEND = "simulator"

_instance: Optional[Any] = None


def _get_sense_instance() -> Optional[Any]:
    """Return a cached Sense HAT (or emulator) instance, if available."""
    global _instance
    if SenseHat is None:
        return None
    if _instance is not None:
        return _instance
    try:
        _instance = SenseHat()
        logger.info("Sense HAT backend initialised: %s", SENSOR_BACKEND)
        return _instance
    except Exception as exc:
        logger.exception("Failed to initialise Sense HAT: %s", exc)
        _instance = None
        return None


def _read_from_sense_hat() -> Optional[Dict[str, float]]:
    sense = _get_sense_instance()
    if sense is None:
        return None
    try:
        return {
            "temperature": float(sense.get_temperature()),
            "humidity": float(sense.get_humidity()),
            "pressure": float(sense.get_pressure()),
        }
    except Exception as exc:
        logger.exception("Sense HAT read failed: %s", exc)
        return None


def _read_from_simulator() -> Dict[str, float]:
    """Plausible random values, useful when no sensor hardware is present."""
    return {
        "temperature": round(random.uniform(20.0, 28.0), 2),
        "humidity": round(random.uniform(40.0, 70.0), 2),
        "pressure": round(random.uniform(1005.0, 1020.0), 2),
    }


def _validate(reading: Dict[str, float]) -> bool:
    """Reject implausible readings before sending them upstream."""
    try:
        t = float(reading["temperature"])
        h = float(reading["humidity"])
        p = float(reading["pressure"])
    except (KeyError, TypeError, ValueError):
        return False
    if not -50 <= t <= 100:
        return False
    if not 0 <= h <= 100:
        return False
    if not 300 <= p <= 1200:
        return False
    return True


def read_reading() -> Optional[Dict[str, Any]]:
    """
    Return a single validated, normalised reading dict, or None if no source
    produced a usable value.
    """
    reading = _read_from_sense_hat()
    if reading is None:
        reading = _read_from_simulator()

    if not _validate(reading):
        logger.warning("Rejected implausible reading: %s", reading)
        return None

    return {
        "temperature": round(reading["temperature"], 2),
        "humidity": round(reading["humidity"], 2),
        "pressure": round(reading["pressure"], 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def get_backend_name() -> str:
    return SENSOR_BACKEND


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Backend:", get_backend_name())
    print("Reading:", read_reading())
