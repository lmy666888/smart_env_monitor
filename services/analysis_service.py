import logging
from typing import Dict, List, Any, Optional
from config import Config

# logger
logger = logging.getLogger("smart_env_monitor.analysis")

# minimum points for trend check
MIN_TREND_POINTS = 5


# get temperature list safely
def _safe_temperature_list(rows: List[Any]) -> List[float]:
    """extract temperature values"""
    temperatures = []
    for row in rows:
        try:
            temperatures.append(float(row["temperature"]))
        except (KeyError, TypeError, ValueError):
            continue

    return temperatures



# detect sudden change
def detect_spike_or_drop(
    temperatures: List[float],
    threshold: float = Config.SPIKE_THRESHOLD
) -> str:
    """check spike or drop"""
    if len(temperatures) < 2:
        return "Not enough data to detect sudden spike or drop."

    recent_change = temperatures[-1] - temperatures[-2]

    if recent_change > threshold:
        return f"Sudden spike detected: +{recent_change:.2f}°C"

    if recent_change < -threshold:
        return f"Sudden drop detected: {recent_change:.2f}°C"

    return "No sudden spike or drop detected."

# detect overall trend
def detect_trend(temperatures: List[float]) -> str:
    """check overall trend"""
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

    logger.debug(
        "Trend analysis: +count=%s -count=%s total_change=%.2f",
        positive_count,
        negative_count,
        total_change
    )
    if positive_count >= total_steps * 0.7 and total_change > 0:
        return "Overall upward trend detected."

    if negative_count >= total_steps * 0.7 and total_change < 0:
        return "Overall downward trend detected."

    return "No clear overall trend detected."



# predict threshold crossing
def predict_threshold_exceedance(
    temperatures: List[float],
    temp_min: float,
    temp_max: float,
    interval_seconds: int = 5
) -> str:
    """predict next threshold crossing"""
    if len(temperatures) < MIN_TREND_POINTS:
        return "Not enough data for prediction."
    avg_change = (temperatures[-1] - temperatures[0]) / (len(temperatures) - 1)
    current_temp = temperatures[-1]

    stability_threshold = getattr(Config, "STABILITY_THRESHOLD", 0.1)

    logger.debug(
        "Prediction analysis: avg_change=%.3f current_temp=%.2f",
        avg_change,
        current_temp
    )
    if abs(avg_change) < stability_threshold:
        return "Temperature is relatively stable; no threshold exceedance predicted soon."

    # going up
    if avg_change > 0 and current_temp < temp_max:
        steps = (temp_max - current_temp) / avg_change
        if steps > 0:
            seconds = steps * interval_seconds
            if seconds < 60:
                return f"Temperature may exceed the upper threshold in about {seconds:.0f} seconds."
            return f"Temperature may exceed the upper threshold in about {seconds / 60:.1f} minutes."
    # going down
    if avg_change < 0 and current_temp > temp_min:
        steps = (current_temp - temp_min) / abs(avg_change)
        if steps > 0:
            seconds = steps * interval_seconds
            if seconds < 60:
                return f"Temperature may fall below the lower threshold in about {seconds:.0f} seconds."
            return f"Temperature may fall below the lower threshold in about {seconds / 60:.1f} minutes."

    return "No threshold exceedance predicted based on the current trend."




# main entry for analysis
def analyze_temperature_trend(
    rows: List[Any],
    settings: Optional[Any],
    interval_seconds: int = 5
) -> Dict[str, str]:
    """run full analysis"""
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
            logger.warning("Analysis skipped: insufficient temperature data.")
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

    except (KeyError, TypeError, ValueError) as exc:
        logger.exception("Analysis failed due to invalid input: %s", exc)
        return {
            "spike_drop": "Analysis unavailable due to invalid input data.",
            "trend": "Analysis unavailable due to invalid input data.",
            "prediction": "Prediction unavailable due to invalid input data."
        }