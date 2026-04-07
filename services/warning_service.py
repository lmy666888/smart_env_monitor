"""
warnings_util.py

Utility functions for generating environmental warnings based on
sensor readings and user-defined threshold settings.

This module supports:
1. Web interface warning generation
2. Sense HAT / emulator warning display
3. Simple status summary for UI use
"""

from typing import List, Dict, Optional

# Try importing Sense HAT.
# If unavailable, the rest of the system will still work.
try:
    from sense_hat import SenseHat
    SENSE_AVAILABLE = True
except ImportError:
    SenseHat = None
    SENSE_AVAILABLE = False


def generate_warnings(latest, settings) -> List[str]:
    """
    Generate warning messages for temperature, humidity, and pressure
    based on the latest sensor reading and current threshold settings.

    Args:
        latest: A dict-like object (e.g. sqlite3.Row) containing:
                - temperature
                - humidity
                - pressure
        settings: A dict-like object containing:
                - temp_min, temp_max
                - humidity_min, humidity_max
                - pressure_min, pressure_max

    Returns:
        List[str]: A list of warning messages. Empty if all values are in range.
    """
    warnings = []

    if not latest or not settings:
        warnings.append("Warning system unavailable: missing sensor data or settings.")
        return warnings

    try:
        temperature = float(latest["temperature"])
        humidity = float(latest["humidity"])
        pressure = float(latest["pressure"])

        temp_min = float(settings["temp_min"])
        temp_max = float(settings["temp_max"])
        humidity_min = float(settings["humidity_min"])
        humidity_max = float(settings["humidity_max"])
        pressure_min = float(settings["pressure_min"])
        pressure_max = float(settings["pressure_max"])
    except (KeyError, TypeError, ValueError):
        warnings.append("Warning system error: invalid sensor data or threshold settings.")
        return warnings

    # Temperature warnings
    if temperature < temp_min:
        warnings.append(
            f"Temperature is too low: {temperature:.2f}°C (min: {temp_min:.2f}°C)"
        )
    elif temperature > temp_max:
        warnings.append(
            f"Temperature is too high: {temperature:.2f}°C (max: {temp_max:.2f}°C)"
        )

    # Humidity warnings
    if humidity < humidity_min:
        warnings.append(
            f"Humidity is too low: {humidity:.2f}% (min: {humidity_min:.2f}%)"
        )
    elif humidity > humidity_max:
        warnings.append(
            f"Humidity is too high: {humidity:.2f}% (max: {humidity_max:.2f}%)"
        )

    # Pressure warnings
    if pressure < pressure_min:
        warnings.append(
            f"Pressure is too low: {pressure:.2f} hPa (min: {pressure_min:.2f} hPa)"
        )
    elif pressure > pressure_max:
        warnings.append(
            f"Pressure is too high: {pressure:.2f} hPa (max: {pressure_max:.2f} hPa)"
        )

    return warnings


def get_warning_status(latest, settings) -> Dict[str, object]:
    """
    Return a structured warning status object for frontend use.

    Args:
        latest: Latest sensor reading row/dict.
        settings: Current threshold settings row/dict.

    Returns:
        dict: {
            "has_warning": bool,
            "count": int,
            "messages": List[str],
            "level": "normal" | "warning" | "error"
        }
    """
    warnings = generate_warnings(latest, settings)

    if warnings and (
        "unavailable" in warnings[0].lower() or "error" in warnings[0].lower()
    ):
        return {
            "has_warning": True,
            "count": len(warnings),
            "messages": warnings,
            "level": "error"
        }

    return {
        "has_warning": len(warnings) > 0,
        "count": len(warnings),
        "messages": warnings,
        "level": "warning" if warnings else "normal"
    }


def get_status_color(latest, settings):
    """
    Return an RGB color tuple representing system status for Sense HAT display.

    Green  = normal
    Red    = warning
    Yellow = data/config issue
    """
    warnings = generate_warnings(latest, settings)

    if warnings and (
        "unavailable" in warnings[0].lower() or "error" in warnings[0].lower()
    ):
        return (255, 255, 0)  # Yellow

    if warnings:
        return (255, 0, 0)  # Red

    return (0, 255, 0)  # Green


def get_short_warning_text(warnings: List[str]) -> str:
    """
    Convert detailed warnings into a short message for Sense HAT scrolling text.

    Args:
        warnings: List of detailed warning strings.

    Returns:
        str: Short summary message.
    """
    if not warnings:
        return "ALL OK"

    short_parts = []

    for msg in warnings:
        lower_msg = msg.lower()

        if "temperature" in lower_msg and "low" in lower_msg:
            short_parts.append("TEMP LOW")
        elif "temperature" in lower_msg and "high" in lower_msg:
            short_parts.append("TEMP HIGH")

        elif "humidity" in lower_msg and "low" in lower_msg:
            short_parts.append("HUM LOW")
        elif "humidity" in lower_msg and "high" in lower_msg:
            short_parts.append("HUM HIGH")

        elif "pressure" in lower_msg and "low" in lower_msg:
            short_parts.append("PRESS LOW")
        elif "pressure" in lower_msg and "high" in lower_msg:
            short_parts.append("PRESS HIGH")

        elif "unavailable" in lower_msg or "error" in lower_msg:
            short_parts.append("SYSTEM ERROR")

    return " | ".join(short_parts) if short_parts else "WARNING"


def display_warnings_on_sense_hat(latest, settings) -> bool:
    """
    Display warning status on the Sense HAT / emulator.

    Behavior:
    - Green screen if everything is normal
    - Red screen + scrolling text if warnings exist
    - Yellow screen + error text if data/settings are invalid

    Args:
        latest: Latest sensor reading row/dict.
        settings: Current threshold settings row/dict.

    Returns:
        bool: True if display update succeeded, False otherwise.
    """
    if not SENSE_AVAILABLE:
        return False

    try:
        sense = SenseHat()
        warnings = generate_warnings(latest, settings)
        color = get_status_color(latest, settings)

        # Fill the LED matrix with the current status color
        sense.clear(color)

        # Scroll text only when there is a warning or error
        if warnings:
            short_text = get_short_warning_text(warnings)
            sense.show_message(short_text, text_colour=color, scroll_speed=0.05)

        return True
    except Exception as e:
        print(f"[SENSE HAT WARNING DISPLAY ERROR] {e}")
        return False


def warning_banner_text(latest, settings) -> str:
    """
    Create a single-line warning banner text for the web interface.

    Args:
        latest: Latest sensor reading row/dict.
        settings: Current threshold settings row/dict.

    Returns:
        str: Human-readable summary for UI banner.
    """
    warnings = generate_warnings(latest, settings)

    if not warnings:
        return "All environmental readings are within the safe threshold range."

    return " | ".join(warnings)