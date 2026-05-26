"""Sense HAT / sense_emu sensor reads with fallbacks."""

import logging
import os
import random
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple

from config import Config

logger = logging.getLogger("smart_env_monitor.sensor")

try:
    from sense_emu import SenseHat as _EmulatorSenseHat  # type: ignore
    EMULATOR_IMPORTED = True
except Exception:
    _EmulatorSenseHat = None
    EMULATOR_IMPORTED = False

try:
    from sense_hat import SenseHat as _RealSenseHat  # type: ignore
    REAL_HAT_IMPORTED = True
except Exception:
    _RealSenseHat = None
    REAL_HAT_IMPORTED = False


SOURCE_REAL_HAT = "real_sense_hat"
SOURCE_EMULATOR = "sense_emu"
SOURCE_MOCK = "mock"
SOURCE_UNKNOWN = "unknown"

_sense_instance: Optional[Any] = None
_active_source: str = SOURCE_UNKNOWN
_init_attempted: bool = False
_last_read_source: Optional[str] = None
_last_error_logged_at: Dict[str, float] = {}

_mock_state: Dict[str, float] = {
    "temperature": 23.0,
    "humidity": 55.0,
    "pressure": 1013.0,
}


def _throttled_warning(key: str, message: str, *args: Any) -> None:
    if Config.DEBUG:
        logger.warning(message, *args)
        return

    throttle = max(1, int(getattr(Config, "LOG_THROTTLE_SECONDS", 60)))
    now = time.monotonic()
    last = _last_error_logged_at.get(key, 0.0)
    if now - last >= throttle:
        logger.warning(message, *args)
        _last_error_logged_at[key] = now


def _init_sense_instance() -> Tuple[Optional[Any], str]:
    """Try sense_emu first, then real HAT, then mock."""
    if Config.USE_MOCK_SENSOR:
        logger.info("USE_MOCK_SENSOR=true; sensor source forced to mock.")
        return None, SOURCE_MOCK

    candidates = []
    forced = os.environ.get("SENSOR_BACKEND", "").strip().lower()
    if forced == "sense_emu" and EMULATOR_IMPORTED:
        candidates.append((_EmulatorSenseHat, SOURCE_EMULATOR))
    elif forced in ("sense_hat", "real_sense_hat") and REAL_HAT_IMPORTED:
        candidates.append((_RealSenseHat, SOURCE_REAL_HAT))
    else:
        if EMULATOR_IMPORTED:
            candidates.append((_EmulatorSenseHat, SOURCE_EMULATOR))
        if REAL_HAT_IMPORTED:
            candidates.append((_RealSenseHat, SOURCE_REAL_HAT))

    for cls, label in candidates:
        try:
            instance = cls()
            logger.info("Sensor backend initialised: %s", label)
            return instance, label
        except Exception as exc:
            logger.warning("Sensor backend %s init failed: %s", label, exc)

    logger.warning(
        "No Sense HAT backend available; falling back to mock data source."
    )
    return None, SOURCE_MOCK


def get_sense_instance() -> Optional[Any]:
    global _sense_instance, _active_source, _init_attempted
    if _init_attempted:
        return _sense_instance
    _sense_instance, _active_source = _init_sense_instance()
    _init_attempted = True
    return _sense_instance


def get_sensor_source_name(use_simulation_fallback: bool = False) -> str:
    if not _init_attempted:
        get_sense_instance()
    if _last_read_source is not None:
        return _last_read_source
    return _active_source


def is_sense_hat_available() -> bool:
    return get_sense_instance() is not None


def validate_sensor_values(temperature: Any, humidity: Any, pressure: Any) -> bool:
    try:
        t = float(temperature)
        h = float(humidity)
        p = float(pressure)
    except (TypeError, ValueError):
        return False
    if not -40 <= t <= 100:
        return False
    if not 0 <= h <= 100:
        return False
    if not 800 <= p <= 1200:
        return False
    return True


def normalize_sensor_values(
    temperature: float, humidity: float, pressure: float
) -> Dict[str, float]:
    return {
        "temperature": round(float(temperature), 2),
        "humidity": round(float(humidity), 2),
        "pressure": round(float(pressure), 2),
    }


def _safe_call(error_key: str, fn: Callable[[], float]) -> Optional[float]:
    try:
        value = fn()
    except Exception as exc:
        _throttled_warning(error_key, "%s failed: %s", error_key, exc)
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        _throttled_warning(error_key, "%s returned non-numeric value: %r", error_key, value)
        return None


def _raw_temperature(sense: Any) -> Optional[float]:
    for method_name in (
        "get_temperature_from_pressure",
        "get_temperature_from_humidity",
        "get_temperature",
    ):
        fn = getattr(sense, method_name, None)
        if fn is None:
            continue
        value = _safe_call(f"sensor.temperature.{method_name}", fn)
        if value is not None:
            return value
    _throttled_warning(
        "sensor.temperature.raw_none",
        "All temperature methods failed for this poll (no raw value).",
    )
    return None


def _raw_humidity(sense: Any) -> Optional[float]:
    fn = getattr(sense, "get_humidity", None)
    if fn is not None:
        value = _safe_call("sensor.humidity.get_humidity", fn)
        if value is not None:
            return value
    _throttled_warning(
        "sensor.humidity.raw_none",
        "Humidity read failed for this poll (no raw value).",
    )
    return None


def _raw_pressure(sense: Any) -> Optional[float]:
    fn = getattr(sense, "get_pressure", None)
    if fn is not None:
        value = _safe_call("sensor.pressure.get_pressure", fn)
        if value is not None:
            return value
    _throttled_warning(
        "sensor.pressure.raw_none",
        "Pressure read failed for this poll (no raw value).",
    )
    return None


def _mock_upload_allowed() -> bool:
    return bool(getattr(Config, "DEMO_MODE", False)) and bool(
        getattr(Config, "MOCK_UPLOAD_ENABLED", False)
    )


def _read_from_mock() -> Dict[str, float]:
    _mock_state["temperature"] += random.uniform(-0.3, 0.3)
    _mock_state["humidity"] += random.uniform(-1.0, 1.0)
    _mock_state["pressure"] += random.uniform(-0.4, 0.4)
    _mock_state["temperature"] = max(15.0, min(32.0, _mock_state["temperature"]))
    _mock_state["humidity"] = max(20.0, min(85.0, _mock_state["humidity"]))
    _mock_state["pressure"] = max(990.0, min(1030.0, _mock_state["pressure"]))
    return normalize_sensor_values(
        _mock_state["temperature"],
        _mock_state["humidity"],
        _mock_state["pressure"],
    )


def read_from_emulator() -> Optional[Dict[str, float]]:
    global _last_read_source

    sense = get_sense_instance()
    if sense is None:
        if _mock_upload_allowed():
            _last_read_source = SOURCE_MOCK
            return _read_from_mock()
        _last_read_source = SOURCE_UNKNOWN
        logger.warning(
            "No Sense device available; mock fallback disabled (set DEMO_MODE=true "
            "and MOCK_UPLOAD_ENABLED=true for demo uploads, or use device/mock_uploader.py)."
        )
        return None

    raw_t = _raw_temperature(sense)
    raw_h = _raw_humidity(sense)
    raw_p = _raw_pressure(sense)
    logger.info(
        "Raw sense device readings (pre-validation): temperature=%r humidity=%r pressure=%r backend=%s",
        raw_t,
        raw_h,
        raw_p,
        _active_source,
    )

    if raw_t is None or raw_h is None or raw_p is None:
        _throttled_warning(
            "sensor.raw_incomplete",
            "Incomplete raw reading (missing channel); mock fallback disabled unless demo mode.",
        )
        if _mock_upload_allowed():
            _last_read_source = SOURCE_MOCK
            return _read_from_mock()
        _last_read_source = SOURCE_UNKNOWN
        return None

    reading = normalize_sensor_values(raw_t, raw_h, raw_p)
    if not validate_sensor_values(
        reading["temperature"], reading["humidity"], reading["pressure"]
    ):
        _throttled_warning(
            "sensor.validation",
            "Sensor reading out of plausible range %s; mock fallback disabled unless demo mode.",
            reading,
        )
        if _mock_upload_allowed():
            _last_read_source = SOURCE_MOCK
            return _read_from_mock()
        _last_read_source = SOURCE_UNKNOWN
        return None

    _last_read_source = _active_source
    return reading


def read_sensor_data(use_simulation_fallback: bool = False) -> Optional[Dict[str, float]]:
    return read_from_emulator()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("source:", get_sensor_source_name())
    for _ in range(3):
        print("reading:", read_from_emulator())
        time.sleep(0.5)
