import threading

from flask import Flask, render_template, jsonify, request

from config import get_config
from database.database import (
    init_db,
    insert_sensor_data,
    get_latest_data,
    get_recent_temperature_data,
    get_recent_sensor_data,
    get_settings,
    update_settings,
)
from warnings_util import (
    generate_warnings,
    get_warning_status,
    warning_banner_text,
)
from services.analysis_service import analyze_temperature_trend
from services.display_service import (
    update_warning_display,
    show_startup_message,
)
from sensors.sensor_reader import (
    start_background_collection,
    get_sensor_source_name,
)

app = Flask(__name__)
app.config.from_object(get_config())


@app.route("/")
def index():
    """
    Render the main dashboard page.
    """
    return render_template("index.html")


@app.route("/api/data", methods=["GET"])
def api_data():
    """
    Return all data required by the frontend dashboard:
    - latest sensor reading
    - current threshold settings
    - warnings and warning summary
    - temperature analysis result
    - historical chart data
    - sensor source information
    """
    try:
        latest = get_latest_data()
        settings = get_settings() or {}
        recent_temp = get_recent_temperature_data(20)
        recent_rows = get_recent_sensor_data(app.config.get("TREND_WINDOW", 5))

        warnings = generate_warnings(latest, settings) if latest and settings else []

        warning_status = (
            get_warning_status(latest, settings)
            if latest and settings
            else {
                "has_warning": True,
                "count": 1,
                "messages": ["No monitoring data available."],
                "level": "error",
            }
        )

        analysis_result = (
            analyze_temperature_trend(
                recent_rows,
                settings,
                interval_seconds=app.config.get("SENSOR_INTERVAL", 5),
            )
            if recent_rows and settings
            else {
                "spike_drop": "No analysis data available.",
                "trend": "No analysis data available.",
                "prediction": "No analysis data available.",
            }
        )

        chart_labels = [row["timestamp"] for row in recent_temp]
        chart_values = [row["temperature"] for row in recent_temp]

        return jsonify(
            {
                "success": True,
                "latest": dict(latest) if latest else None,
                "settings": dict(settings) if settings else None,
                "warnings": warnings,
                "warnings_count": len(warnings),
                "warning_status": warning_status,
                "warning_banner": (
                    warning_banner_text(latest, settings)
                    if latest and settings
                    else "No monitoring data available."
                ),
                "analysis": analysis_result,
                "chart_labels": chart_labels,
                "chart_values": chart_values,
                "sensor_source": get_sensor_source_name(
                    use_simulation_fallback=app.config.get("USE_SIMULATION", False)
                ),
            }
        )

    except Exception as e:
        return jsonify(
            {
                "success": False,
                "message": "Failed to load monitoring data.",
                "error": str(e),
            }
        ), 500


@app.route("/api/settings", methods=["POST"])
def api_settings():
    """
    Update warning threshold settings for temperature, humidity, and pressure.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "Missing JSON payload."}), 400

    try:
        temp_min = float(data["temp_min"])
        temp_max = float(data["temp_max"])
        humidity_min = float(data["humidity_min"])
        humidity_max = float(data["humidity_max"])
        pressure_min = float(data["pressure_min"])
        pressure_max = float(data["pressure_max"])
    except (KeyError, ValueError, TypeError):
        return jsonify({"success": False, "message": "Invalid input."}), 400

    if temp_min >= temp_max:
        return jsonify(
            {"success": False, "message": "Temperature min must be less than max."}
        ), 400

    if humidity_min >= humidity_max:
        return jsonify(
            {"success": False, "message": "Humidity min must be less than max."}
        ), 400

    if pressure_min >= pressure_max:
        return jsonify(
            {"success": False, "message": "Pressure min must be less than max."}
        ), 400

    success = update_settings(
        temp_min,
        temp_max,
        humidity_min,
        humidity_max,
        pressure_min,
        pressure_max,
    )

    if not success:
        return jsonify(
            {"success": False, "message": "Failed to update settings."}
        ), 500

    latest = get_latest_data()
    settings = get_settings() or {}
    if latest and settings:
        update_warning_display(latest, settings)

    return jsonify(
        {
            "success": True,
            "message": "Settings updated successfully.",
            "settings": dict(settings) if settings else None,
        }
    )


@app.route("/api/simulate", methods=["POST"])
def api_simulate():
    """
    Insert manual sensor data for testing or demonstration.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "Missing JSON payload."}), 400

    try:
        temperature = float(data["temperature"])
        humidity = float(data["humidity"])
        pressure = float(data["pressure"])
    except (KeyError, ValueError, TypeError):
        return jsonify({"success": False, "message": "Invalid sensor values."}), 400

    success = insert_sensor_data(temperature, humidity, pressure)
    if not success:
        return jsonify(
            {"success": False, "message": "Failed to store sensor data."}
        ), 500

    latest = get_latest_data()
    settings = get_settings() or {}
    if latest and settings:
        update_warning_display(latest, settings)

    warnings = generate_warnings(latest, settings) if latest and settings else []

    return jsonify(
        {
            "success": True,
            "message": "Sensor data stored.",
            "latest": dict(latest) if latest else None,
            "warnings": warnings,
        }
    )


@app.route("/api/health", methods=["GET"])
def api_health():
    """
    Health-check endpoint for troubleshooting.
    """
    try:
        latest = get_latest_data()
        settings = get_settings()

        return jsonify(
            {
                "success": True,
                "status": "ok",
                "database": "connected",
                "latest_data_available": latest is not None,
                "settings_available": settings is not None,
                "sensor_source": get_sensor_source_name(
                    use_simulation_fallback=app.config.get("USE_SIMULATION", False)
                ),
            }
        )
    except Exception as e:
        return jsonify(
            {
                "success": False,
                "status": "error",
                "message": "System health check failed.",
                "error": str(e),
            }
        ), 500


@app.route("/api/debug", methods=["GET"])
def api_debug():
    """
    Debug endpoint for quick inspection of current database state.
    """
    latest = get_latest_data()
    settings = get_settings()

    return jsonify(
        {
            "latest": dict(latest) if latest else None,
            "settings": dict(settings) if settings else None,
            "sensor_source": get_sensor_source_name(
                use_simulation_fallback=app.config.get("USE_SIMULATION", False)
            ),
        }
    )


if __name__ == "__main__":
    print("[SYSTEM] Starting Smart Environment Monitoring System...")
    print(
        f"[CONFIG] Host={app.config.get('HOST', '0.0.0.0')} "
        f"Port={app.config.get('PORT', 5000)}"
    )
    print(
        f"[SYSTEM] Sensor Interval: {app.config.get('SENSOR_INTERVAL', 5)}s"
    )

    init_db()
    show_startup_message()

    sensor_thread = threading.Thread(
        target=start_background_collection,
        kwargs={
            "interval_seconds": app.config.get("SENSOR_INTERVAL", 5),
            "use_simulation_fallback": app.config.get("USE_SIMULATION", False),
        },
        daemon=True,
    )
    sensor_thread.start()
    print("[SYSTEM] Sensor background thread started.")

    app.run(
        host=app.config.get("HOST", "0.0.0.0"),
        port=app.config.get("PORT", 5000),
        debug=app.config.get("DEBUG", False),
    )