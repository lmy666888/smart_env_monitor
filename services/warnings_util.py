from typing import Any, Dict, List

# generate warnings based on values


def generate_warnings(latest: Any, settings: Any) -> List[str]:
    """check warnings"""
    if not latest or not settings:
        return ["No data available."]

    warnings = []
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

    except Exception:
        return ["Invalid sensor data or settings."]

    # temperature
    if temperature < temp_min:
        warnings.append(f"Temperature too low ({temperature:.2f}°C)")
    elif temperature > temp_max:
        warnings.append(f"Temperature too high ({temperature:.2f}°C)")



    # humidity
    if humidity < humidity_min:
        warnings.append(f"Humidity too low ({humidity:.2f}%)")
    elif humidity > humidity_max:
        warnings.append(f"Humidity too high ({humidity:.2f}%)")


    # pressure
    if pressure < pressure_min:
        warnings.append(f"Pressure too low ({pressure:.2f} hPa)")
    elif pressure > pressure_max:
        (warnings.append(f"Pressure too high ({pressure:.2f} hPa)"))

    return warnings


def _severity_level(warnings: List[str]) -> str:
    """Map messages to normal / warning / critical for UI."""
    if not warnings:
        return "normal"
    if warnings == ["No data available."] or warnings == ["Invalid sensor data or settings."]:
        return "error"
    # Multiple simultaneous environmental breaches → critical
    kinds = set()
    for w in warnings:
        wl = w.lower()
        if "temperature" in wl:
            kinds.add("t")
        if "humidity" in wl:
            kinds.add("h")
        if "pressure" in wl:
            kinds.add("p")
    if len(warnings) >= 3 or len(kinds) >= 2:
        return "critical"
    return "warning"


def get_warning_status(latest: Any, settings: Any) -> Dict[str, object]:
    """build warning status"""
    warnings = generate_warnings(latest, settings)

    if warnings == ["No data available."] or warnings == ["Invalid sensor data or settings."]:
        return {
            "has_warning": True,
            "count": len(warnings),
            "messages": warnings,
            "level": "error",
        }

    level = _severity_level(warnings)
    return {
        "has_warning": len(warnings) > 0,
        "count": len(warnings),
        "messages": warnings,
        "level": level if warnings else "normal",
    }


# get color for display

def get_status_color(latest: Any, settings: Any):
    """get status color"""
    warnings = generate_warnings(latest, settings)

    if warnings == ["No data available."] or warnings == ["Invalid sensor data or settings."]:
        return (255, 255, 0)

    if warnings:
        return (255, 0, 0)

    return (0, 255, 0)


# convert warnings to short text
def get_short_warning_text(warnings: List[str]) -> str:
    """short warning text"""
    if not warnings:
        return "ALL OK"
    mapping = []

    for msg in warnings:
        msg_lower = msg.lower()

        if "temperature" in msg_lower:
            mapping.append("TEMP")
        elif "humidity" in msg_lower:
            mapping.append("HUM")
        elif "pressure" in msg_lower:
            mapping.append("PRESS")
        elif "data" in msg_lower:
            mapping.append("ERROR")

    return " | ".join(mapping) if mapping else "WARNING"


# text for web banner
def warning_banner_text(latest: Any, settings: Any) -> str:
    """banner text"""
    warnings = generate_warnings(latest, settings)
    if not warnings:
        return "All readings are within normal ranges."

    if warnings[0] in ["No data available.", "Invalid sensor data or settings."]:
        return "SYSTEM ERROR"

    return " | ".join(warnings)