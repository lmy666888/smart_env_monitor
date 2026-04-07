"""
analysis_service.py

Service module for analysing recent temperature readings.

This module provides:
1. Sudden spike/drop detection
2. Overall trend detection
3. Basic threshold exceedance prediction
"""

from typing import Dict, List, Any, Optional
from config import Config


MIN_TREND_POINTS = 5


def _safe_temperature_list(rows: List[Any]) -> List[float]:
    """
    Safely extract temperature values from database rows or dictionaries.

    Args:
        rows: Iterable rows containing a 'temperature' field.

    Returns:
        List[float]: Clean temperature list. Invalid rows are skipped.
    """
    temperatures = []

    for row in rows:
        try:
            temperatures.append(float(row["temperature"]))
        except (KeyError, TypeError, ValueError):
            continue

    return temperatures


def detect_spike_or_drop(temperatures: List[float], threshold: float = Config.SPIKE_THRESHOLD) -> str:
    """
    Detect whether the latest reading changed sharply compared with the previous reading.

    Args:
        temperatures: Recent temperature values in chronological order.
        threshold: Minimum absolute change required to count as spike/drop.

    Returns:
        str: Human-readable spike/drop status.
    """
    if len(temperatures) < 2:
        return "Not enough data to detect sudden spike or drop."

    recent_change = temperatures[-1] - temperatures[-2]

    if recent_change > threshold:
        return f"Sudden spike detected: +{recent_change:.2f}°C"
    if recent_change < -threshold:
        return f"Sudden drop detected: {recent_change:.2f}°C"

    return "No sudden spike or drop detected."


def detect_trend(temperatures: List[float]) -> str:
    """
    Detect the overall direction of temperature change using recent readings.

    This method is more robust than requiring perfectly monotonic data.
    It checks whether most recent changes are positive or negative and
    whether the total change supports the same direction.

    Args:
        temperatures: Recent temperature values in chronological order.

    Returns:
        str: Human-readable trend status.
    """
    if len(temperatures) < MIN_TREND_POINTS:
        return "Not enough data to determine a reliable trend."

    differences = [
        temperatures[i + 1] - temperatures[i]
        for i in range(len(temperatures) - 1)
    ]

    positive_count = sum(1 for d in differences if d > 0)
    negative_count = sum(1 for d in differences if d < 0)
    total_change = temperatures[-1] - temperatures[0]
    total_steps = len(differences)

    if positive_count >= total_steps * 0.7 and total_change > 0:
        return "Overall upward trend detected."

    if negative_count >= total_steps * 0.7 and total_change < 0:
        return "Overall downward trend detected."

    return "No clear overall trend detected."


def predict_threshold_exceedance(
    temperatures: List[float],
    temp_min: float,
    temp_max: float,
    interval_seconds: int = 5
) -> str:
    """
    Estimate when temperature may exceed the upper threshold
    or drop below the lower threshold based on average change rate.

    Args:
        temperatures: Recent temperature values in chronological order.
        temp_min: Lower threshold.
        temp_max: Upper threshold.
        interval_seconds: Time gap between consecutive readings.

    Returns:
        str: Human-readable prediction result.
    """
    if len(temperatures) < MIN_TREND_POINTS:
        return "Not enough data for prediction."

    avg_change = (temperatures[-1] - temperatures[0]) / (len(temperatures) - 1)
    current_temp = temperatures[-1]

    if abs(avg_change) < 0.1:
        return "Temperature is relatively stable; no threshold exceedance predicted soon."

    if avg_change > 0 and current_temp < temp_max:
        steps = (temp_max - current_temp) / avg_change
        if steps > 0:
            seconds = steps * interval_seconds
            if seconds < 60:
                return f"Temperature may exceed the upper threshold in about {seconds:.0f} seconds."
            return f"Temperature may exceed the upper threshold in about {seconds / 60:.1f} minutes."

    if avg_change < 0 and current_temp > temp_min:
        steps = (current_temp - temp_min) / abs(avg_change)
        if steps > 0:
            seconds = steps * interval_seconds
            if seconds < 60:
                return f"Temperature may fall below the lower threshold in about {seconds:.0f} seconds."
            return f"Temperature may fall below the lower threshold in about {seconds / 60:.1f} minutes."

    return "No threshold exceedance predicted based on the current trend."


def analyze_temperature_trend(
    rows: List[Any],
    settings: Optional[Any],
    interval_seconds: int = 5
) -> Dict[str, str]:
    """
    Main analysis function used by the Flask API.

    It evaluates:
    - sudden spike/drop
    - overall trend
    - threshold exceedance prediction

    Args:
        rows: Recent sensor data rows, each containing a 'temperature' field.
        settings: Current threshold settings row/dict containing 'temp_min' and 'temp_max'.
        interval_seconds: Time gap between recent readings.

    Returns:
        Dict[str, str]: Analysis result dictionary.
    """
    result = {
        "spike_drop": "No sudden spike or drop detected.",
        "trend": "Not enough data to determine a reliable trend.",
        "prediction": "Not enough data for prediction."
    }

    try:
        if not rows or not settings:
            return result

        temperatures = _safe_temperature_list(rows)
        if len(temperatures) < 2:
            return result

        temp_min = float(settings["temp_min"])
        temp_max = float(settings["temp_max"])

        result["spike_drop"] = detect_spike_or_drop(temperatures)
        result["trend"] = detect_trend(temperatures)
        result["prediction"] = predict_threshold_exceedance(
            temperatures,
            temp_min=temp_min,
            temp_max=temp_max,
            interval_seconds=interval_seconds
        )

        return result

    except (KeyError, TypeError, ValueError):
        return {
            "spike_drop": "Analysis unavailable due to invalid input data.",
            "trend": "Analysis unavailable due to invalid input data.",
            "prediction": "Prediction unavailable due to invalid input data."
        }