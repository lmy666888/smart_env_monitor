"""
display_service.py

Service module for displaying system status and warnings on the Sense HAT
or Sense HAT emulator.

Display behaviour:
- Green: all readings normal
- Red: threshold warning present
- Yellow: data/config/system issue
"""

from typing import Any, Tuple

from config import Config
from warnings_util import generate_warnings, get_short_warning_text, get_status_color

try:
    from sense_hat import SenseHat
    SENSE_AVAILABLE = True
except ImportError:
    SenseHat = None
    SENSE_AVAILABLE = False


def is_sense_hat_available() -> bool:
    """
    Check whether Sense HAT library is available and enabled by configuration.
    """
    return SENSE_AVAILABLE and Config.ENABLE_SENSE_HAT


def get_display_status(latest: Any, settings: Any) -> dict:
    """
    Create a structured display status summary.
    """
    try:
        warnings = generate_warnings(latest, settings)
        color = get_status_color(latest, settings)
        text = get_short_warning_text(warnings)

        return {
            "warnings": warnings,
            "warning_count": len(warnings),
            "color": color,
            "text": text,
            "sense_available": is_sense_hat_available()
        }
    except Exception:
        return {
            "warnings": ["Display status unavailable due to system error."],
            "warning_count": 1,
            "color": (255, 255, 0),
            "text": "SYSTEM ERROR",
            "sense_available": is_sense_hat_available()
        }


def clear_display(color: Tuple[int, int, int] = (0, 0, 0)) -> bool:
    """
    Clear the Sense HAT LED matrix with a given color.
    """
    if not is_sense_hat_available():
        return False

    try:
        sense = SenseHat()
        sense.clear(color)
        return True
    except Exception as e:
        print(f"[DISPLAY CLEAR ERROR] {e}")
        return False


def show_status_color(latest: Any, settings: Any) -> bool:
    """
    Fill the Sense HAT LED matrix using status color only.
    """
    if not is_sense_hat_available():
        return False

    try:
        color = get_status_color(latest, settings)
        sense = SenseHat()
        sense.clear(color)
        return True
    except Exception as e:
        print(f"[DISPLAY STATUS COLOR ERROR] {e}")
        return False


def scroll_warning_text(latest: Any, settings: Any, scroll_speed: float = 0.05) -> bool:
    """
    Scroll a short warning summary on the Sense HAT.
    """
    if not is_sense_hat_available():
        return False

    try:
        warnings = generate_warnings(latest, settings)
        text = get_short_warning_text(warnings)
        color = get_status_color(latest, settings)

        sense = SenseHat()
        sense.show_message(text, text_colour=color, scroll_speed=scroll_speed)
        return True
    except Exception as e:
        print(f"[DISPLAY SCROLL ERROR] {e}")
        return False


def update_warning_display(latest: Any, settings: Any, scroll_speed: float = 0.05) -> bool:
    """
    Main display update function for the project.
    """
    if not is_sense_hat_available():
        return False

    try:
        warnings = generate_warnings(latest, settings)
        color = get_status_color(latest, settings)

        sense = SenseHat()
        sense.clear(color)

        if warnings:
            text = get_short_warning_text(warnings)
            sense.show_message(text, text_colour=color, scroll_speed=scroll_speed)

        return True
    except Exception as e:
        print(f"[DISPLAY UPDATE ERROR] {e}")
        return False


def show_startup_message() -> bool:
    """
    Display a short startup message when the system launches.
    """
    if not is_sense_hat_available():
        return False

    try:
        sense = SenseHat()
        sense.clear((0, 0, 255))
        sense.show_message("ENV MONITOR READY", text_colour=(0, 255, 255), scroll_speed=0.05)
        return True
    except Exception as e:
        print(f"[DISPLAY STARTUP ERROR] {e}")
        return False


def show_system_error(message: str = "SYSTEM ERROR") -> bool:
    """
    Display a general system error on the Sense HAT.
    """
    if not is_sense_hat_available():
        return False

    try:
        sense = SenseHat()
        sense.clear((255, 255, 0))
        sense.show_message(message, text_colour=(255, 255, 0), scroll_speed=0.05)
        return True
    except Exception as e:
        print(f"[DISPLAY SYSTEM ERROR] {e}")
        return False