import logging
from typing import Any, Dict, Optional, Tuple
from config import Config
from warnings_util import (
    generate_warnings,
    get_short_warning_text,
    get_status_color,
)



logger = logging.getLogger("smart_env_monitor.display")


# detect which backend is available
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




# reuse instance
_sense_instance: Optional[Any] = None


# check if display is usable
def is_sense_hat_available() -> bool:
    """check display available"""
    return bool(SenseHat is not None and Config.ENABLE_SENSE_HAT)
# get backend name
def get_display_backend_name() -> str:
    """get backend name"""
    if not Config.ENABLE_SENSE_HAT:
        return "disabled"
    return SENSE_BACKEND

# get or create instance
def get_sense_instance() -> Optional[Any]:
    """get display instance"""
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
# fix rgb values
def _normalize_color(color: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """clamp rgb"""
    try:
        r, g, b = color
        return (
            max(0, min(255, int(r))),
            max(0, min(255, int(g))),
            max(0, min(255, int(b))),
        )
    except Exception:
        return (255, 255, 0)

# build short text
def _safe_short_text(warnings: list[str]) -> str:
    """short display text"""
    try:
        text = get_short_warning_text(warnings)
        if not text:
            return "ALL OK"
        return str(text)[:64]
    except Exception:
        return "SYSTEM ERROR"


# fallback error status
def _build_display_error_status(message: str) -> Dict[str, Any]:
    """build error status"""
    return {
        "warnings": [message],
        "warning_count": 1,
        "color": (255, 255, 0),
        "text": "SYSTEM ERROR",
        "sense_available": is_sense_hat_available(),
        "backend": get_display_backend_name(),
    }

# build display status
def get_display_status(latest: Any, settings: Any) -> Dict[str, Any]:
    """get display status"""
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

# clear screen
def clear_display(color: Tuple[int, int, int] = (0, 0, 0)) -> bool:
    """clear display"""
    sense = get_sense_instance()
    if sense is None:
        logger.warning("Display clear skipped: backend unavailable.")
        return False

    try:
        safe_color = _normalize_color(color)
        sense.clear(safe_color)
        return True
    except Exception as exc:
        logger.exception("Display clear failed: %s", exc)
        return False

# show only color
def show_status_color(latest: Any, settings: Any) -> bool:
    """show status color"""
    sense = get_sense_instance()
    if sense is None:
        logger.warning("Status color display skipped: backend unavailable.")
        return False

    try:
        color = _normalize_color(get_status_color(latest, settings))
        sense.clear(color)
        return True
    except Exception as exc:
        logger.exception("Display status color update failed: %s", exc)
        return False




# scroll warning text
def scroll_warning_text(
    latest: Any,
    settings: Any,
    scroll_speed: float = 0.05
) -> bool:
    """scroll warning text"""
    sense = get_sense_instance()
    if sense is None:
        logger.warning("Warning text scroll skipped: backend unavailable.")
        return False

    try:
        warnings = generate_warnings(latest, settings)
        text = _safe_short_text(warnings)
        color = _normalize_color(get_status_color(latest, settings))

        sense.show_message(
            text,
            text_colour=color,
            scroll_speed=float(scroll_speed),
        )
        return True
    except Exception as exc:
        logger.exception("Display warning text scroll failed: %s", exc)
        return False


# main display update
def update_warning_display(
    latest: Any,
    settings: Any,
    scroll_speed: float = 0.05
) -> bool:
    """update display"""
    sense = get_sense_instance()
    if sense is None:
        logger.warning("Display update skipped: backend unavailable.")
        return False

    try:
        warnings = generate_warnings(latest, settings)
        color = _normalize_color(get_status_color(latest, settings))

        # set background first
        sense.clear(color)

        # scroll only if warning exists
        if warnings:
            text = _safe_short_text(warnings)
            sense.show_message(
                text,
                text_colour=color,
                scroll_speed=float(scroll_speed),
            )

        logger.debug(
            "Display updated. backend=%s warnings=%s",
            get_display_backend_name(),
            len(warnings),
        )
        return True

    except Exception as exc:
        logger.exception("Display update failed: %s", exc)
        return False

# startup message
def show_startup_message(scroll_speed: float = 0.05) -> bool:
    """show startup"""
    sense = get_sense_instance()
    if sense is None:
        logger.warning("Startup message skipped: backend unavailable.")
        return False
    try:
        sense.clear((0, 0, 255))
        sense.show_message(
            "ENV MONITOR READY",
            text_colour=(0, 255, 255),
            scroll_speed=float(scroll_speed),
        )
        logger.info("Startup message displayed.")
        return True
    except Exception as exc:
        logger.exception("Display startup message failed: %s", exc)
        return False

# show error message
def show_system_error(
    message: str = "SYSTEM ERROR",
    scroll_speed: float = 0.05
) -> bool:
    """show error"""
    sense = get_sense_instance()
    if sense is None:
        logger.warning("System error display skipped: backend unavailable.")
        return False


    try:
        text = str(message).strip() or "SYSTEM ERROR"
        text = text[:64]

        sense.clear((255, 255, 0))
        sense.show_message(
            text,
            text_colour=(255, 255, 0),
            scroll_speed=float(scroll_speed),
        )
        logger.warning("System error shown: %s", text)
        return True
    except Exception as exc:
        logger.exception("Display system error failed: %s", exc)
        return False