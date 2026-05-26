"""Sense HAT LED display — shows warnings as colours and scrolling text."""

import logging
from typing import Any, Dict, List, Optional, Tuple

from config import Config
from services.warnings_util import (
    generate_warnings,
    get_short_warning_text,
    get_status_color,
)

logger = logging.getLogger("smart_env_monitor.display")

SENSE_BACKEND = "unavailable"
SenseHat = None

try:
    from sense_emu import SenseHat as EmulatorSenseHat
    SenseHat = EmulatorSenseHat
    SENSE_BACKEND = "sense_emu"
except ImportError:
    try:
        from sense_hat import SenseHat as PhysicalSenseHat
        SenseHat = PhysicalSenseHat
        SENSE_BACKEND = "sense_hat"
    except ImportError:
        SenseHat = None
        SENSE_BACKEND = "unavailable"

_sense_instance: Optional[Any] = None


def is_sense_hat_available() -> bool:
    return bool(SenseHat is not None and Config.ENABLE_SENSE_HAT)


def get_display_backend_name() -> str:
    if not Config.ENABLE_SENSE_HAT:
        return "disabled"
    return SENSE_BACKEND


def get_sense_instance() -> Optional[Any]:
    global _sense_instance
    if not is_sense_hat_available():
        return None
    if _sense_instance is not None:
        return _sense_instance
    try:
        _sense_instance = SenseHat()
        logger.info("Display backend initialized: %s", get_display_backend_name())
        return _sense_instance
    except Exception as exc:
        logger.exception("Failed to initialize display backend: %s", exc)
        _sense_instance = None
        return None


def _normalize_color(color: Tuple[int, int, int]) -> Tuple[int, int, int]:
    try:
        r, g, b = color
        return (
            max(0, min(255, int(r))),
            max(0, min(255, int(g))),
            max(0, min(255, int(b))),
        )
    except Exception:
        return (255, 255, 0)


def _safe_short_text(warnings: List[str]) -> str:
    try:
        text = get_short_warning_text(warnings)
        if not text:
            return "ALL OK"
        return str(text)[:64]
    except Exception:
        return "SYSTEM ERROR"


def _build_display_error_status(message: str) -> Dict[str, Any]:
    return {
        "warnings": [message],
        "warning_count": 1,
        "color": (255, 255, 0),
        "text": "SYSTEM ERROR",
        "sense_available": is_sense_hat_available(),
        "backend": get_display_backend_name(),
    }


def get_display_status(latest: Any, settings: Any) -> Dict[str, Any]:
    if not is_sense_hat_available():
        return {
            "warnings": ["Display backend is unavailable or disabled."],
            "warning_count": 1,
            "color": (255, 255, 0),
            "text": "DISPLAY OFF",
            "sense_available": False,
            "backend": get_display_backend_name(),
        }

    try:
        warnings = generate_warnings(latest, settings)
        color = _normalize_color(get_status_color(latest, settings))
        text = _safe_short_text(warnings)
        return {
            "warnings": warnings,
            "warning_count": len(warnings),
            "color": color,
            "text": text,
            "sense_available": True,
            "backend": get_display_backend_name(),
        }
    except Exception as exc:
        logger.exception("Failed to build display status: %s", exc)
        return _build_display_error_status(
            "Display status unavailable due to system error."
        )


def clear_display(color: Tuple[int, int, int] = (0, 0, 0)) -> bool:
    sense = get_sense_instance()
    if sense is None:
        return False
    try:
        sense.clear(_normalize_color(color))
        return True
    except Exception as exc:
        logger.exception("Display clear failed: %s", exc)
        return False


def show_status_color(latest: Any, settings: Any) -> bool:
    sense = get_sense_instance()
    if sense is None:
        return False
    try:
        color = _normalize_color(get_status_color(latest, settings))
        sense.clear(color)
        return True
    except Exception as exc:
        logger.exception("Display status color update failed: %s", exc)
        return False


def scroll_warning_text(
    latest: Any,
    settings: Any,
    scroll_speed: float = 0.05
) -> bool:
    sense = get_sense_instance()
    if sense is None:
        return False
    try:
        warnings = generate_warnings(latest, settings)
        text = _safe_short_text(warnings)
        color = _normalize_color(get_status_color(latest, settings))
        sense.show_message(text, text_colour=color, scroll_speed=float(scroll_speed))
        return True
    except Exception as exc:
        logger.exception("Display warning text scroll failed: %s", exc)
        return False


def update_warning_display(
    latest: Any,
    settings: Any,
    scroll_speed: float = 0.05
) -> bool:
    sense = get_sense_instance()
    if sense is None:
        return False
    try:
        warnings = generate_warnings(latest, settings)
        color = _normalize_color(get_status_color(latest, settings))
        sense.clear(color)
        if warnings:
            text = _safe_short_text(warnings)
            sense.show_message(text, text_colour=color, scroll_speed=float(scroll_speed))
        return True
    except Exception as exc:
        logger.exception("Display update failed: %s", exc)
        return False


def show_startup_message(scroll_speed: float = 0.05) -> bool:
    sense = get_sense_instance()
    if sense is None:
        return False
    try:
        sense.clear((0, 0, 255))
        sense.show_message("ENV MONITOR READY", text_colour=(0, 255, 255), scroll_speed=float(scroll_speed))
        logger.info("Startup message displayed.")
        return True
    except Exception as exc:
        logger.exception("Display startup message failed: %s", exc)
        return False


def show_system_error(
    message: str = "SYSTEM ERROR",
    scroll_speed: float = 0.05
) -> bool:
    sense = get_sense_instance()
    if sense is None:
        return False
    try:
        text = (str(message).strip() or "SYSTEM ERROR")[:64]
        sense.clear((255, 255, 0))
        sense.show_message(text, text_colour=(255, 255, 0), scroll_speed=float(scroll_speed))
        logger.warning("System error shown: %s", text)
        return True
    except Exception as exc:
        logger.exception("Display system error failed: %s", exc)
        return False
