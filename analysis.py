def analyze_temperature_trend(rows, settings, interval_seconds=5):
    """
    Analyze recent temperature readings to detect:
    1. Sudden spikes or drops
    2. Overall upward or downward trends
    3. Basic prediction of threshold exceedance time

    Args:
        rows: Recent sensor data rows, each containing a 'temperature' field.
        settings: Threshold settings row containing 'temp_min' and 'temp_max'.
        interval_seconds: Approximate time gap between consecutive readings.

    Returns:
        dict: Analysis results for spike/drop, trend, and prediction.
    """
    result = {
        "spike_drop": "No sudden spike or drop detected.",
        "trend": "Not enough data to determine a reliable trend.",
        "prediction": "Not enough data for prediction."
    }

    if not rows or len(rows) < 2 or not settings:
        return result

    try:
        temperatures = [float(row["temperature"]) for row in rows]
        upper_limit = float(settings["temp_max"])
        lower_limit = float(settings["temp_min"])
    except (KeyError, TypeError, ValueError):
        result["trend"] = "Analysis failed due to invalid data."
        result["prediction"] = "Prediction unavailable due to invalid data."
        return result

    # 1. Sudden spike or drop using the last two readings
    recent_change = temperatures[-1] - temperatures[-2]
    if recent_change > 3:
        result["spike_drop"] = f"Sudden spike detected: +{recent_change:.2f}°C"
    elif recent_change < -3:
        result["spike_drop"] = f"Sudden drop detected: {recent_change:.2f}°C"

    # 2. Trend detection
    if len(temperatures) >= 5:
        differences = [temperatures[i + 1] - temperatures[i] for i in range(len(temperatures) - 1)]
        positive_count = sum(1 for d in differences if d > 0)
        negative_count = sum(1 for d in differences if d < 0)
        total_change = temperatures[-1] - temperatures[0]

        if positive_count >= len(differences) * 0.7 and total_change > 0:
            result["trend"] = "Overall upward trend detected."
        elif negative_count >= len(differences) * 0.7 and total_change < 0:
            result["trend"] = "Overall downward trend detected."
        else:
            result["trend"] = "No clear overall trend detected."

    # 3. Threshold exceedance prediction
    if len(temperatures) >= 5:
        avg_change = (temperatures[-1] - temperatures[0]) / (len(temperatures) - 1)
        current_temp = temperatures[-1]

        # Avoid unstable predictions when slope is too small
        if abs(avg_change) < 0.1:
            result["prediction"] = "Temperature is relatively stable; no threshold exceedance predicted soon."
            return result

        if avg_change > 0 and current_temp < upper_limit:
            steps = (upper_limit - current_temp) / avg_change
            if steps > 0:
                seconds = steps * interval_seconds
                if seconds < 60:
                    result["prediction"] = (
                        f"Temperature may exceed the upper threshold in about {seconds:.0f} seconds."
                    )
                else:
                    result["prediction"] = (
                        f"Temperature may exceed the upper threshold in about {seconds / 60:.1f} minutes."
                    )

        elif avg_change < 0 and current_temp > lower_limit:
            steps = (current_temp - lower_limit) / abs(avg_change)
            if steps > 0:
                seconds = steps * interval_seconds
                if seconds < 60:
                    result["prediction"] = (
                        f"Temperature may fall below the lower threshold in about {seconds:.0f} seconds."
                    )
                else:
                    result["prediction"] = (
                        f"Temperature may fall below the lower threshold in about {seconds / 60:.1f} minutes."
                    )

    return result