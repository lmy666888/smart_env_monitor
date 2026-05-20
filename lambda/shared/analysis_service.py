"""
AWS Lambda intelligent analysis service.

Provides:
- spike/drop detection
- trend analysis
- volatility analysis
- threshold prediction
"""

import logging
from typing import Dict, List, Any, Optional



logger = logging.getLogger("smart_env_monitor.analysis")

MIN_TREND_POINTS = 5


def _safe_temperature_list(rows: List[Any]) -> List[float]:
    """Extract valid temperature values safely."""
    temperatures = []

    for row in rows:
        try:
            temperatures.append(float(row["temperature"]))
        except (KeyError, TypeError, ValueError):
            continue

    return temperatures


def detect_spike_or_drop(
    temperatures: List[float],
    threshold: float = 5.0
) -> str:
    """Detect sudden spike or drop."""

    if len(temperatures) < 2:
        return "Not enough data to detect sudden spike or drop."

    recent_change = temperatures[-1] - temperatures[-2]

    logger.debug(
        "Spike/drop analysis: recent_change=%.2f threshold=%.2f",
        recent_change,
        threshold
    )

    if recent_change > threshold:
        return f"Sudden spike detected: +{recent_change:.2f}°C"

    if recent_change < -threshold:
        return f"Sudden drop detected: {recent_change:.2f}°C"

    return "No sudden spike or drop detected."


def detect_trend(temperatures: List[float]) -> str:
    """
    Enhanced intelligent trend analysis.

    Supports:
    - upward trend
    - downward trend
    - stable pattern
    - high volatility detection
    """

    if len(temperatures) < MIN_TREND_POINTS:
        return "Not enough data to determine a reliable trend."

    try:
        recent = temperatures[-20:]

        first_temp = recent[0]
        last_temp = recent[-1]

        max_temp = max(recent)
        min_temp = min(recent)

        total_change = last_temp - first_temp
        volatility = max_temp - min_temp

        logger.debug(
            (
                "Trend analysis: "
                "first=%.2f last=%.2f "
                "max=%.2f min=%.2f "
                "change=%.2f volatility=%.2f"
            ),
            first_temp,
            last_temp,
            max_temp,
            min_temp,
            total_change,
            volatility
        )

        # Highly unstable / rapidly fluctuating readings
        if volatility >= 20:
            return (
                "Temperature readings are highly volatile "
                "with rapid fluctuations detected."
            )

        # Upward trend
        if total_change >= 5:
            return "Temperature shows an upward trend."

        # Downward trend
        if total_change <= -5:
            return "Temperature shows a downward trend."

        # Stable condition
        return "Temperature remains relatively stable."

    except Exception as exc:
        logger.exception("Trend analysis failed: %s", exc)
        return "No clear overall trend detected."


def predict_threshold_exceedance(
    temperatures: List[float],
    temp_min: float,
    temp_max: float,
    interval_seconds: int = 5
) -> str:
    """Predict future threshold exceedance."""

    if len(temperatures) < MIN_TREND_POINTS:
        return "Not enough data for prediction."

    avg_change = (
        (temperatures[-1] - temperatures[0]) /
        (len(temperatures) - 1)
    )

    current_temp = temperatures[-1]

    stability_threshold = 0.1

    logger.debug(
        "Prediction analysis: avg_change=%.3f current_temp=%.2f",
        avg_change,
        current_temp
    )

    # Stable readings
    if abs(avg_change) < stability_threshold:
        return (
            "Temperature is relatively stable; "
            "no threshold exceedance predicted soon."
        )

    # Predict upper threshold exceedance
    if avg_change > 0 and current_temp < temp_max:

        steps = (temp_max - current_temp) / avg_change

        if steps > 0:

            seconds = steps * interval_seconds

            if seconds < 60:
                return (
                    "Temperature may exceed the upper threshold "
                    f"in about {seconds:.0f} seconds."
                )

            return (
                "Temperature may exceed the upper threshold "
                f"in about {seconds / 60:.1f} minutes."
            )

    # Predict lower threshold exceedance
    if avg_change < 0 and current_temp > temp_min:

        steps = (
            (current_temp - temp_min) /
            abs(avg_change)
        )

        if steps > 0:

            seconds = steps * interval_seconds

            if seconds < 60:
                return (
                    "Temperature may fall below the lower threshold "
                    f"in about {seconds:.0f} seconds."
                )

            return (
                "Temperature may fall below the lower threshold "
                f"in about {seconds / 60:.1f} minutes."
            )

    return (
        "No threshold exceedance predicted "
        "based on the current trend."
    )


def analyze_temperature_trend(
    rows: List[Any],
    settings: Optional[Any],
    interval_seconds: int = 5
) -> Dict[str, str]:
    """
    Main intelligent analysis entrypoint.
    """

    result = {
        "spike_drop": "No sudden spike or drop detected.",
        "trend": "Not enough data to determine a reliable trend.",
        "prediction": "Not enough data for prediction."
    }

    try:

        if not rows or not settings:
            logger.warning(
                "Analysis skipped: missing rows or settings."
            )
            return result

        temperatures = _safe_temperature_list(rows)

        if len(temperatures) < 2:
            logger.warning(
                "Analysis skipped: insufficient temperature data."
            )
            return result

        temp_min = float(settings["temp_min"])
        temp_max = float(settings["temp_max"])

        result["spike_drop"] = detect_spike_or_drop(
            temperatures
        )

        result["trend"] = detect_trend(
            temperatures
        )

        result["prediction"] = predict_threshold_exceedance(
            temperatures,
            temp_min=temp_min,
            temp_max=temp_max,
            interval_seconds=interval_seconds
        )

        logger.info(
            "Analysis complete: %s",
            result
        )

        return result

    except (KeyError, TypeError, ValueError) as exc:

        logger.exception(
            "Analysis failed due to invalid input: %s",
            exc
        )

        return {
            "spike_drop": (
                "Analysis unavailable due to invalid input data."
            ),
            "trend": (
                "Analysis unavailable due to invalid input data."
            ),
            "prediction": (
                "Prediction unavailable due to invalid input data."
            )
        }