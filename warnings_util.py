"""
warnings_util.py

Utility functions for generating warnings and display-related status.
"""

from typing import Any, List, Tuple


def _safe_get(data: Any, key: str, default=None):
    """
    Safely extract value from dict-like or sqlite Row.
    """
    try:
        return data[key]
    except Exception:
        return default


# -----------------------------
# 1. 基础 warnings
# -----------------------------
def generate_warnings(data: Any, settings: Any) -> List[str]:
    """
    Generate warning messages based on sensor data and thresholds.
    """
    warnings = []

    if data is None or settings is None:
        return ["No data available."]

    try:
        temperature = float(_safe_get(data, "temperature"))
        humidity = float(_safe_get(data, "humidity"))
        pressure = float(_safe_get(data, "pressure"))

        if temperature < settings["temp_min"] or temperature > settings["temp_max"]:
            warnings.append(f"Temperature out of range ({temperature:.2f}°C)")

        if humidity < settings["humidity_min"] or humidity > settings["humidity_max"]:
            warnings.append(f"Humidity out of range ({humidity:.2f}%)")

        if pressure < settings["pressure_min"] or pressure > settings["pressure_max"]:
            warnings.append(f"Pressure out of range ({pressure:.2f} hPa)")

    except Exception:
        return ["Invalid sensor data."]

    return warnings


# -----------------------------
# 2. 状态颜色（Sense HAT / Emulator）
# -----------------------------
def get_status_color(data: Any, settings: Any) -> Tuple[int, int, int]:
    """
    Return RGB color representing system status:
    - Green: normal
    - Red: warning
    - Yellow: system/data issue
    """
    if data is None or settings is None:
        return (255, 255, 0)  # yellow

    warnings = generate_warnings(data, settings)

    if warnings and warnings != ["No data available."]:
        return (255, 0, 0)  # red

    return (0, 255, 0)  # green


# -----------------------------
# 3. 简短 warning 文本（LED滚动）
# -----------------------------
def get_short_warning_text(warnings: List[str]) -> str:
    """
    Convert warning list into a short display-friendly message.
    """
    if not warnings:
        return "ALL OK"

    if len(warnings) == 1:
        return warnings[0][:30]

    return f"{len(warnings)} WARNINGS"


# -----------------------------
# 4. 前端状态汇总（API）
# -----------------------------
def get_warning_status(data: Any, settings: Any) -> dict:
    """
    Return structured warning status for frontend.
    """
    if data is None or settings is None:
        return {
            "has_warning": True,
            "count": 1,
            "messages": ["No data available."],
            "level": "error"
        }

    warnings = generate_warnings(data, settings)

    if not warnings:
        return {
            "has_warning": False,
            "count": 0,
            "messages": [],
            "level": "normal"
        }

    return {
        "has_warning": True,
        "count": len(warnings),
        "messages": warnings,
        "level": "warning"
    }


# -----------------------------
# 5. Banner 文本（网页顶部）
# -----------------------------
def warning_banner_text(data: Any, settings: Any) -> str:
    """
    Return a single-line summary for UI banner.
    """
    status = get_warning_status(data, settings)

    if status["level"] == "error":
        return "SYSTEM ERROR: No data available."

    if status["level"] == "normal":
        return "All environmental readings are within normal ranges."

    return f"{status['count']} warning(s) detected."