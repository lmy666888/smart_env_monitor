import logging
import time
from typing import Any, Dict, Optional
from database.database import insert_sensor_data
# logger
logger = logging.getLogger("smart_env_monitor.sensor")
# try load emulator
try:
    from sense_emu import SenseHat
    EMULATOR_AVAILABLE = True
except ImportError:
    SenseHat = None
    EMULATOR_AVAILABLE = False

# reuse emulator instance
_sense_instance: Optional[Any] = None



# check emulator available
def is_sense_hat_available() -> bool:
    """check emulator installed"""
    return EMULATOR_AVAILABLE

# get sensor source name
def get_sensor_source_name(use_simulation_fallback: bool = False) -> str:
    """return current sensor source"""
    if EMULATOR_AVAILABLE:
        return "Sense HAT Emulator"
    return "No Sensor Source Available"

# get or create emulator instance
def get_sense_instance() -> Optional[Any]:
    """get emulator instance"""
    global _sense_instance

    if not EMULATOR_AVAILABLE:
        return None

    if _sense_instance is not None:
        return _sense_instance

    try:
        _sense_instance = SenseHat()
        logger.info("Sense HAT emulator initialized successfully.")
        return _sense_instance
    except Exception as exc:
        logger.exception("Failed to initialize Sense HAT emulator: %s", exc)
        _sense_instance = None
        return None



# basic sanity check for values
def validate_sensor_values(
    temperature: float,
    humidity: float,
    pressure: float
) -> bool:
    """check if values look reasonable"""
    try:
        temperature = float(temperature)
        humidity = float(humidity)
        pressure = float(pressure)
    except (TypeError, ValueError):
        return False

    if not (-50 <= temperature <= 100):
        return False
    if not (0 <= humidity <= 100):
        return False
    if not (300 <= pressure <= 1200):
        return False

    return True

# round values
def normalize_sensor_values(
    temperature: float,
    humidity: float,
    pressure: float
) -> Dict[str, float]:
    """round values to 2 dp"""
    return {
        "temperature": round(float(temperature), 2),
        "humidity": round(float(humidity), 2),
        "pressure": round(float(pressure), 2),
    }



# read from emulator
def read_from_emulator() -> Optional[Dict[str, float]]:
    """read sensor data"""
    if not EMULATOR_AVAILABLE:
        logger.warning("Sensor read skipped: sense_emu is not installed.")
        return None

    sense = get_sense_instance()
    if sense is None:
        logger.warning("Sensor read skipped: emulator instance unavailable.")
        return None

    try:
        raw_temperature = sense.get_temperature()
        raw_humidity = sense.get_humidity()
        raw_pressure = sense.get_pressure()

        reading = normalize_sensor_values(
            raw_temperature,
            raw_humidity,
            raw_pressure,
        )

        if not validate_sensor_values(
            reading["temperature"],
            reading["humidity"],
            reading["pressure"],
        ):
            logger.warning(
                "Invalid emulator reading rejected: T=%s, H=%s, P=%s",
                reading["temperature"],
                reading["humidity"],
                reading["pressure"],
            )
            return None


        return reading

    except Exception as exc:
        logger.exception("Emulator read failed: %s", exc)
        return None



# main read entry
def read_sensor_data(use_simulation_fallback: bool = False) -> Optional[Dict[str, float]]:
    """get one reading"""
    return read_from_emulator()
# read and save once
def collect_and_store_reading(use_simulation_fallback: bool = False) -> bool:
    """read and store data"""
    reading = read_sensor_data(use_simulation_fallback=use_simulation_fallback)

    if not reading:
        logger.warning("Sensor collection failed: no valid emulator reading available.")
        return False

    success = insert_sensor_data(
        reading["temperature"],
        reading["humidity"],
        reading["pressure"],
    )

    if not success:
        logger.error("Sensor storage failed: database insert was unsuccessful.")
        return False

    logger.info(
        "Emulator reading stored successfully: T=%.2f°C, H=%.2f%%, P=%.2f hPa",
        reading["temperature"],
        reading["humidity"],
        reading["pressure"],
    )
    return True

# background loop
def start_background_collection(
    interval_seconds: int = 5,
    use_simulation_fallback: bool = False,
    max_iterations: Optional[int] = None
) -> None:
    """run loop to collect data"""
    safe_interval = max(1, int(interval_seconds))
    logger.info(
        "Background collection started. interval=%ss max_iterations=%s",
        safe_interval,
        max_iterations,
    )
    iteration = 0
    while True:
        try:
            success = collect_and_store_reading(
                use_simulation_fallback=use_simulation_fallback
            )
            if not success:
                logger.warning("Background collection cycle completed with failure.")
        except Exception as exc:
            logger.exception("Background collection error: %s", exc)

        iteration += 1
        if max_iterations is not None and iteration >= max_iterations:
            logger.info("Background collection stopped after %s iterations.", iteration)
            break

        time.sleep(safe_interval)