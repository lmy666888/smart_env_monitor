"""
Sensor reader.

Goals (read this first):

* Never crash the Flask app or background worker because one sensor read
  failed.
* Avoid the well-known `OSError: Humidity Init Failed` cascade on
  sense_emu by trying temperature methods in a safe order:
  `get_temperature_from_pressure` first (which does **not** touch the
  humidity sensor), then `get_temperature_from_humidity`, then plain
  `get_temperature`.
* Wrap every individual sensor read in its own try/except and fall back
  to a reasonable physical default if that read fails.
* If the emulator (or real HAT) cannot be initialised at all, switch
  permanently into a deterministic mock data source so the dashboard,
  warnings and chart keep working.
* Throttle repeated identical errors so the log does not get flooded with
  the same traceback every cycle.

Sources reported via `get_sensor_source_name()`:
    - "real_sense_hat" : physical Sense HAT on a Raspberry Pi
    - "sense_emu"      : Sense HAT desktop emulator
    - "mock"           : built-in random-walk fallback
"""

import logging
import random
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple

from config import Config

# Database insert is no longer used from this module (cloud ingest in ``sensor.collector``).

logger = logging.getLogger("smart_env_monitor.sensor")

# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

# Try importing the desktop emulator first (developer laptops).
try:
    from sense_emu import SenseHat as _EmulatorSenseHat  # type: ignore
    EMULATOR_IMPORTED = True
except Exception:  # pragma: no cover - import guard
    _EmulatorSenseHat = None
    EMULATOR_IMPORTED = False

# Real Sense HAT (only matters on a Raspberry Pi).
try:
    from sense_hat import SenseHat as _RealSenseHat  # type: ignore
    REAL_HAT_IMPORTED = True
except Exception:  # pragma: no cover - import guard
    _RealSenseHat = None
    REAL_HAT_IMPORTED = False


SOURCE_REAL_HAT = "real_sense_hat"
SOURCE_EMULATOR = "sense_emu"
SOURCE_MOCK = "mock"
SOURCE_UNKNOWN = "unknown"

# ---------------------------------------------------------------------------
# Cached state
# ---------------------------------------------------------------------------

_sense_instance: Optional[Any] = None
_active_source: str = SOURCE_UNKNOWN
_init_attempted: bool = False

# {error_key: monotonic_seconds_of_last_log}
_last_error_logged_at: Dict[str, float] = {}

# Mock random-walk state. Starts near plausible "indoor" values so the
# dashboard looks sensible immediately.
_mock_state: Dict[str, float] = {
    "temperature": 23.0,
    "humidity": 55.0,
    "pressure": 1013.0,
}


# ---------------------------------------------------------------------------
# Throttled logging helper
# ---------------------------------------------------------------------------

def _throttled_warning(key: str, message: str, *args: Any) -> None:
    """
    Log `message` at WARNING level, but at most once per
    Config.LOG_THROTTLE_SECONDS for the same `key`.

    In DEBUG mode the throttling is disabled so engineers can see every
    failure during local development.
    """
    if Config.DEBUG:
        logger.warning(message, *args)
        return

    throttle = max(1, int(getattr(Config, "LOG_THROTTLE_SECONDS", 60)))
    now = time.monotonic()
    last = _last_error_logged_at.get(key, 0.0)
    if now - last >= throttle:
        logger.warning(message, *args)
        _last_error_logged_at[key] = now


# ---------------------------------------------------------------------------
# Backend initialisation
# ---------------------------------------------------------------------------

def _init_sense_instance() -> Tuple[Optional[Any], str]:
    """
    Try to instantiate a Sense HAT (emulator or real). If both fail or the
    user has set USE_MOCK_SENSOR=1, return (None, SOURCE_MOCK).

    Priority order (per project requirements - Raspberry Pi + Sense HAT
    Emulator as primary source):

      1. sense_emu  (preferred, works on Pi desktop, macOS, Windows, Linux)
      2. real Sense HAT  (used when running on a Pi without the emulator)
      3. mock  (deterministic fallback so the dashboard never goes dark)
    """
    if Config.USE_MOCK_SENSOR:
        logger.info("USE_MOCK_SENSOR=true; sensor source forced to mock.")
        return None, SOURCE_MOCK

    candidates = []
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
    """Return the cached HAT instance, initialising once on first call."""
    global _sense_instance, _active_source, _init_attempted
    if _init_attempted:
        return _sense_instance
    _sense_instance, _active_source = _init_sense_instance()
    _init_attempted = True
    return _sense_instance


def get_sensor_source_name(use_simulation_fallback: bool = False) -> str:
    """
    Return one of: "real_sense_hat", "sense_emu", "mock".

    The `use_simulation_fallback` argument is kept for backwards compatibility
    with the legacy Flask app; it is currently ignored.
    """
    if not _init_attempted:
        get_sense_instance()
    return _active_source


def is_sense_hat_available() -> bool:
    """True if a real / emulated HAT instance was successfully created."""
    return get_sense_instance() is not None


# ---------------------------------------------------------------------------
# Validation / normalisation
# ---------------------------------------------------------------------------

def validate_sensor_values(temperature: Any, humidity: Any, pressure: Any) -> bool:
    """Coerce values to float and check they sit in a physically plausible range."""
    try:
        t = float(temperature)
        h = float(humidity)
        p = float(pressure)
    except (TypeError, ValueError):
        return False
    if not -50 <= t <= 100:
        return False
    if not 0 <= h <= 100:
        return False
    if not 300 <= p <= 1200:
        return False
    return True


def normalize_sensor_values(
    temperature: float, humidity: float, pressure: float
) -> Dict[str, float]:
    """Round each value to 2 decimal places for storage / display."""
    return {
        "temperature": round(float(temperature), 2),
        "humidity": round(float(humidity), 2),
        "pressure": round(float(pressure), 2),
    }


# ---------------------------------------------------------------------------
# Safe individual sensor reads
# ---------------------------------------------------------------------------

def _safe_call(error_key: str, fn: Callable[[], float]) -> Optional[float]:
    """Invoke `fn`, returning a float or None (with throttled warning) on error."""
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


def _read_temperature(sense: Any) -> float:
    """
    Try multiple temperature methods in order of safety.

    `get_temperature_from_pressure` is preferred because it does NOT touch
    the humidity sensor, so it survives "Humidity Init Failed" errors.
    """
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
        "sensor.temperature.fallback",
        "All temperature methods failed; using fallback %.2f°C",
        Config.FALLBACK_TEMPERATURE,
    )
    return float(Config.FALLBACK_TEMPERATURE)


def _read_humidity(sense: Any) -> float:
    fn = getattr(sense, "get_humidity", None)
    if fn is not None:
        value = _safe_call("sensor.humidity.get_humidity", fn)
        if value is not None:
            return value
    _throttled_warning(
        "sensor.humidity.fallback",
        "Humidity read failed; using fallback %.2f%%",
        Config.FALLBACK_HUMIDITY,
    )
    return float(Config.FALLBACK_HUMIDITY)


def _read_pressure(sense: Any) -> float:
    fn = getattr(sense, "get_pressure", None)
    if fn is not None:
        value = _safe_call("sensor.pressure.get_pressure", fn)
        if value is not None:
            return value
    _throttled_warning(
        "sensor.pressure.fallback",
        "Pressure read failed; using fallback %.2f hPa",
        Config.FALLBACK_PRESSURE,
    )
    return float(Config.FALLBACK_PRESSURE)


# ---------------------------------------------------------------------------
# Mock source (random walk near plausible values)
# ---------------------------------------------------------------------------

def _read_from_mock() -> Dict[str, float]:
    """Return one mock reading using a smooth random walk."""
    _mock_state["temperature"] += random.uniform(-0.3, 0.3)
    _mock_state["humidity"] += random.uniform(-1.0, 1.0)
    _mock_state["pressure"] += random.uniform(-0.4, 0.4)
    # Clamp to sensible indoor ranges.
    _mock_state["temperature"] = max(15.0, min(32.0, _mock_state["temperature"]))
    _mock_state["humidity"] = max(20.0, min(85.0, _mock_state["humidity"]))
    _mock_state["pressure"] = max(990.0, min(1030.0, _mock_state["pressure"]))
    return normalize_sensor_values(
        _mock_state["temperature"],
        _mock_state["humidity"],
        _mock_state["pressure"],
    )


# ---------------------------------------------------------------------------
# Public read entry points
# ---------------------------------------------------------------------------

def read_from_emulator() -> Optional[Dict[str, float]]:
    """
    Always returns a normalised reading dict (or None only in truly
    impossible situations). When the HAT backend is missing or broken,
    this falls back to the mock source.
    """
    sense = get_sense_instance()
    if sense is None:
        return _read_from_mock()

    temperature = _read_temperature(sense)
    humidity = _read_humidity(sense)
    pressure = _read_pressure(sense)
    reading = normalize_sensor_values(temperature, humidity, pressure)

    if not validate_sensor_values(
        reading["temperature"], reading["humidity"], reading["pressure"]
    ):
        _throttled_warning(
            "sensor.validation",
            "Sensor reading out of plausible range %s; using mock fallback",
            reading,
        )
        return _read_from_mock()
    return reading


def read_sensor_data(use_simulation_fallback: bool = False) -> Optional[Dict[str, float]]:
    """Backwards-compatible alias preserved for the legacy Flask app."""
    return read_from_emulator()


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    logging.basicConfig(level=logging.INFO)
    print("source:", get_sensor_source_name())
    for _ in range(3):
        print("reading:", read_from_emulator())
        time.sleep(0.5)
