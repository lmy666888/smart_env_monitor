"""
sensor_reader.py

Read environmental data from the official Sense HAT emulator (sense_emu).

This module is responsible for:
- reading temperature, humidity, and pressure
- validating readings
- storing readings in the database
- running continuous background collection
"""

import time
from typing import Optional, Dict

from database.database import insert_sensor_data

try:
    from sense_emu import SenseHat
    EMULATOR_AVAILABLE = True
except ImportError:
    SenseHat = None
    EMULATOR_AVAILABLE = False


def is_sense_hat_available() -> bool:
    """
    Check whether the official Sense HAT emulator library is available.
    """
    return EMULATOR_AVAILABLE


def validate_sensor_values(temperature: float, humidity: float, pressure: float) -> bool:
    """
    Validate raw sensor readings to filter out obviously invalid values.

    Args:
        temperature: Temperature in degrees Celsius.
        humidity: Relative humidity percentage.
        pressure: Pressure in hPa / millibars.

    Returns:
        bool: True if values are reasonable, False otherwise.
    """
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


def read_from_emulator() -> Optional[Dict[str, float]]:
    """
    Read temperature, humidity, and pressure from the official Sense HAT emulator.

    Returns:
        dict | None: Sensor values if successful, otherwise None.
    """
    if not EMULATOR_AVAILABLE:
        return None

    try:
        sense = SenseHat()

        temperature = round(float(sense.get_temperature()), 2)
        humidity = round(float(sense.get_humidity()), 2)
        pressure = round(float(sense.get_pressure()), 2)

        if not validate_sensor_values(temperature, humidity, pressure):
            return None

        return {
            "temperature": temperature,
            "humidity": humidity,
            "pressure": pressure
        }

    except Exception as e:
        print(f"[EMULATOR READ ERROR] {e}")
        return None


def read_sensor_data(use_simulation_fallback: bool = False) -> Optional[Dict[str, float]]:
    """
    Read sensor data from the official emulator.

    Args:
        use_simulation_fallback: Ignored in emulator-only mode.

    Returns:
        dict | None: Sensor reading dictionary or None if unavailable.
    """
    return read_from_emulator()


def collect_and_store_reading(use_simulation_fallback: bool = False) -> bool:
    """
    Read one emulator sample and store it in the database.

    Args:
        use_simulation_fallback: Ignored in emulator-only mode.

    Returns:
        bool: True if a valid reading was stored, False otherwise.
    """
    reading = read_sensor_data(use_simulation_fallback=use_simulation_fallback)

    if not reading:
        print("[SENSOR COLLECTION ERROR] No emulator reading available.")
        return False

    success = insert_sensor_data(
        reading["temperature"],
        reading["humidity"],
        reading["pressure"]
    )

    if not success:
        print("[SENSOR STORAGE ERROR] Failed to store sensor reading.")
        return False

    print(
        f"[EMU SENSOR] T={reading['temperature']:.2f}°C, "
        f"H={reading['humidity']:.2f}%, "
        f"P={reading['pressure']:.2f} hPa"
    )
    return True


def start_background_collection(
    interval_seconds: int = 5,
    use_simulation_fallback: bool = False,
    max_iterations: Optional[int] = None
) -> None:
    """
    Start a continuous loop that periodically reads emulator data and stores it.

    This function is suitable for running in a background thread.
    """
    print("[SENSOR READER] Emulator background collection started.")

    iteration = 0
    while True:
        try:
            collect_and_store_reading(use_simulation_fallback=use_simulation_fallback)
        except Exception as e:
            print(f"[BACKGROUND COLLECTION ERROR] {e}")

        iteration += 1
        if max_iterations is not None and iteration >= max_iterations:
            print("[SENSOR READER] Background collection stopped after test iterations.")
            break

        time.sleep(interval_seconds)


def get_sensor_source_name(use_simulation_fallback: bool = False) -> str:
    """
    Return the current sensor source description.
    """
    if EMULATOR_AVAILABLE:
        return "Sense HAT Emulator"
    return "No Sensor Source Available"