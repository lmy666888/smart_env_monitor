import logging
import os
from typing import Any, Dict, List, Optional

SPIKE_THRESHOLD = float(os.getenv("SPIKE_THRESHOLD", "3.0"))
STABILITY_THRESHOLD = float(os.getenv("STABILITY_THRESHOLD", "0.15"))
MIN_TREND_POINTS = int(os.getenv("MIN_TREND_POINTS", "5"))
RECENT_WINDOW = int(os.getenv("RECENT_WINDOW", "8"))

logger = logging.getLogger("smart_env_monitor.analysis")


def _safe_temperature_list(rows: List[Any]) -> List[float]:
    temperatures: List[float] = []

    for row in rows:
        try:
            value = float(row["temperature"])
            if -50 <= value <= 100:
                temperatures.append(value)
        except (KeyError, TypeError, ValueError):
            continue

    return temperatures


def _get_recent_values(temperatures: List[float], window: int = RECENT_WINDOW) -> List[float]:
    if len(temperatures) <= window:
        return temperatures
    return temperatures[-window:]


def detect_spike_or_drop(
    temperatures: List[float],
    threshold: float = SPIKE_THRESHOLD
) -> str:
    if len(temperatures) < 2:
        return "Not enough data to detect sudden spike or drop."

    recent = _get_recent_values(temperatures, 5)
    latest_change = recent[-1] - recent[-2]

    if latest_change >= threshold:
        return f"Sudden temperature spike detected: +{latest_change:.2f}°C since the previous reading."

    if latest_change <= -threshold:
        return f"Sudden temperature drop detected: {latest_change:.2f}°C since the previous reading."

    max_jump = max(
        abs(recent[i] - recent[i - 1])
        for i in range(1, len(recent))
    )

    if max_jump >= threshold:
        return f"Recent temperature instability detected; largest change was {max_jump:.2f}°C."

    return "No sudden spike or drop detected."


def detect_trend(temperatures: List[float]) -> str:
    if len(temperatures) < MIN_TREND_POINTS:
        return "Not enough data to determine a reliable trend."

    recent = _get_recent_values(temperatures, 20)

    first_temp = recent[0]
    last_temp = recent[-1]
    total_change = last_temp - first_temp
    temp_range = max(recent) - min(recent)

    mean = sum(recent) / len(recent)
    variance = sum((t - mean) ** 2 for t in recent) / len(recent)
    std_dev = variance ** 0.5

    logger.debug(
        "Trend analysis: first=%.2f last=%.2f change=%.2f range=%.2f std=%.2f n=%s",
        first_temp,
        last_temp,
        total_change,
        temp_range,
        std_dev,
        len(recent),
    )

    if std_dev >= 3.0 or temp_range >= 6.0:
        return "Temperature readings are volatile with rapid fluctuations detected."

    if abs(total_change) <= 1.0 and std_dev < 1.2:
        return "Temperature is relatively stable."

    if total_change > 2.0:
        return "Temperature is increasing over the recent readings."

    if total_change < -2.0:
        return "Temperature is decreasing over the recent readings."

    return "No clear overall temperature trend detected."


def predict_threshold_exceedance(
    temperatures: List[float],
    temp_min: float,
    temp_max: float,
    interval_seconds: int = 5
) -> str:
    if len(temperatures) < MIN_TREND_POINTS:
        return "Not enough data for prediction."

    current_temp = temperatures[-1]

    # 1. Current-state awareness: already abnormal.
    if current_temp > temp_max:
        diff = current_temp - temp_max
        if diff >= 5:
            return (
                f"Critical: temperature is currently {diff:.2f}°C above the maximum "
                f"threshold ({temp_max:.1f}°C). Immediate attention is recommended."
            )
        return (
            f"Warning: temperature is currently exceeding the maximum threshold "
            f"({temp_max:.1f}°C) by {diff:.2f}°C."
        )

    if current_temp < temp_min:
        diff = temp_min - current_temp
        if diff >= 5:
            return (
                f"Critical: temperature is currently {diff:.2f}°C below the minimum "
                f"threshold ({temp_min:.1f}°C). Immediate attention is recommended."
            )
        return (
            f"Warning: temperature is currently below the minimum threshold "
            f"({temp_min:.1f}°C) by {diff:.2f}°C."
        )

    # 2. Near-threshold awareness.
    upper_margin = temp_max - current_temp
    lower_margin = current_temp - temp_min

    if upper_margin <= 1.0:
        return (
            f"Temperature is very close to the upper threshold. Current margin: "
            f"{upper_margin:.2f}°C."
        )

    if lower_margin <= 1.0:
        return (
            f"Temperature is very close to the lower threshold. Current margin: "
            f"{lower_margin:.2f}°C."
        )

    # 3. Recent-window prediction instead of whole-history average.
    recent = _get_recent_values(temperatures, RECENT_WINDOW)

    if len(recent) < MIN_TREND_POINTS:
        return "Not enough recent data for prediction."

    avg_change = (recent[-1] - recent[0]) / (len(recent) - 1)

    logger.debug(
        "Prediction analysis: current=%.2f avg_recent_change=%.3f temp_min=%.2f temp_max=%.2f",
        current_temp,
        avg_change,
        temp_min,
        temp_max,
    )

    if abs(avg_change) < STABILITY_THRESHOLD:
        return "Temperature is relatively stable; no threshold exceedance predicted soon."

    if avg_change > 0:
        steps = (temp_max - current_temp) / avg_change
        if 0 < steps <= 12:
            seconds = steps * interval_seconds
            if seconds < 60:
                return f"Temperature is rising and may exceed the upper threshold in about {seconds:.0f} seconds."
            return f"Temperature is rising and may exceed the upper threshold in about {seconds / 60:.1f} minutes."
        return "Temperature is rising, but no immediate upper-threshold exceedance is predicted."

    if avg_change < 0:
        steps = (current_temp - temp_min) / abs(avg_change)
        if 0 < steps <= 12:
            seconds = steps * interval_seconds
            if seconds < 60:
                return f"Temperature is falling and may go below the lower threshold in about {seconds:.0f} seconds."
            return f"Temperature is falling and may go below the lower threshold in about {seconds / 60:.1f} minutes."
        return "Temperature is falling, but no immediate lower-threshold exceedance is predicted."

    return "No threshold exceedance predicted based on the current trend."


def analyze_temperature_trend(
    rows: List[Any],
    settings: Optional[Any],
    interval_seconds: int = 5
) -> Dict[str, str]:
    result = {
        "spike_drop": "No sudden spike or drop detected.",
        "trend": "Not enough data to determine a reliable trend.",
        "prediction": "Not enough data for prediction."
    }

    try:
        if not rows or not settings:
            logger.warning("Analysis skipped: missing rows or settings.")
            return result

        temperatures = _safe_temperature_list(rows)

        if len(temperatures) < 2:
            logger.warning("Analysis skipped: insufficient valid temperature data.")
            return result

        temp_min = float(settings["temp_min"])
        temp_max = float(settings["temp_max"])

        if temp_min >= temp_max:
            logger.warning("Analysis skipped: invalid thresholds temp_min >= temp_max.")
            return {
                "spike_drop": "Analysis unavailable due to invalid threshold settings.",
                "trend": "Analysis unavailable due to invalid threshold settings.",
                "prediction": "Prediction unavailable because minimum temperature threshold is not below maximum threshold."
            }

        result["spike_drop"] = detect_spike_or_drop(temperatures)
        result["trend"] = detect_trend(temperatures)
        result["prediction"] = predict_threshold_exceedance(
            temperatures,
            temp_min=temp_min,
            temp_max=temp_max,
            interval_seconds=interval_seconds
        )

        return result

    except (KeyError, TypeError, ValueError) as exc:
        logger.exception("Analysis failed due to invalid input: %s", exc)
        return {
            "spike_drop": "Analysis unavailable due to invalid input data.",
            "trend": "Analysis unavailable due to invalid input data.",
            "prediction": "Prediction unavailable due to invalid input data."
        }