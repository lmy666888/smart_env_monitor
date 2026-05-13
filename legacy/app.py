import logging
import threading
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Dict, Optional
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from config import get_config
from legacy.database import (
    get_latest_data,
    get_recent_sensor_data,
    get_recent_temperature_data,
    get_settings,
    init_db,
    insert_sensor_data,
    update_settings,
)
from sensors.sensor_reader import (
    collect_and_store_reading,
    get_sensor_source_name,
)

from services.analysis_service import analyze_temperature_trend
from legacy.auth_service import (
    build_login_result,
    get_current_username,
    is_logged_in,
    logout_user,
)
from legacy.display_service import (
    get_display_status,
    show_startup_message,
    show_system_error,
    update_warning_display,
)
from warnings_util import (
    generate_warnings,
    get_warning_status,
    warning_banner_text,
)

# app setup
Config = get_config()


app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = app.config.get("SECRET_KEY", "change-this-secret-key")
logging.basicConfig(
    level=getattr(logging, str(app.config.get("LOG_LEVEL", "INFO")).upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


logger = logging.getLogger("smart_env_monitor")

# runtime state
runtime_state: Dict[str, Any] = {
    "app_started_at": datetime.now(timezone.utc).isoformat(),
    "collector_thread_alive": False,
    "last_collection_attempt_at": None,
    "last_collection_success_at": None,
    "last_display_update_at": None,
    "last_error": None,
    "consecutive_collection_failures": 0,
    "total_collection_successes": 0,
    "total_collection_failures": 0,
}


def safe_iso_now() -> str:
    """get current time"""
    return datetime.now(timezone.utc).isoformat()

# convert sqlite row
def row_to_dict(row: Optional[Any]) -> Optional[Dict[str, Any]]:
    """row to dict"""
    if row is None:
        return None
    try:
        return dict(row)
    except Exception:
        return None


def build_success_response(**payload):
    """success response"""
    payload["success"] = True
    return jsonify(payload)


# error
def build_error_response(message: str, status_code: int = 400, **extra):
    """error response"""
    payload = {
        "success": False,
        "message": message,
    }
    payload.update(extra)
    return jsonify(payload), status_code
# login check decorator
def login_required(view_func):
    """require login"""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not is_logged_in():
            if request.path.startswith("/api/"):
                return build_error_response("Authentication required.", 401)
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapper

# validate thresholds
def validate_threshold_payload(data: Dict[str, Any]) -> Dict[str, float]:
    """check threshold input"""
    try:
        values = {
            "temp_min": float(data["temp_min"]),
            "temp_max": float(data["temp_max"]),
            "humidity_min": float(data["humidity_min"]),
            "humidity_max": float(data["humidity_max"]),
            "pressure_min": float(data["pressure_min"]),
            "pressure_max": float(data["pressure_max"]),
        }
    except (KeyError, TypeError, ValueError):
        raise ValueError("Invalid threshold input.")

    if values["temp_min"] >= values["temp_max"]:
        raise ValueError("Temperature minimum must be less than maximum.")
    if values["humidity_min"] >= values["humidity_max"]:
        raise ValueError("Humidity minimum must be less than maximum.")
    if values["pressure_min"] >= values["pressure_max"]:
        raise ValueError("Pressure minimum must be less than maximum.")

    return values
# validate manual input
def validate_simulation_payload(data: Dict[str, Any]) -> Dict[str, float]:
    """check manual sensor input"""
    try:
        values = {
            "temperature": float(data["temperature"]),
            "humidity": float(data["humidity"]),
            "pressure": float(data["pressure"]),
        }
    except (KeyError, TypeError, ValueError):
        raise ValueError("Invalid sensor values.")

    return values




# update display using latest data
def refresh_display_from_latest_data() -> bool:
    """refresh display"""
    latest = get_latest_data()
    settings = get_settings()

    if not latest or not settings:
        logger.warning("Display refresh skipped.")
        return False

    success = update_warning_display(latest, settings)
    if success:
        runtime_state["last_display_update_at"] = safe_iso_now()

    return success


def build_dashboard_payload() -> Dict[str, Any]:
    """build dashboard data"""
    latest = get_latest_data()
    settings = get_settings()
    recent_temp = get_recent_temperature_data(20)
    recent_rows = get_recent_sensor_data(app.config.get("TREND_WINDOW", 5))
    latest_dict = row_to_dict(latest)
    settings_dict = row_to_dict(settings)
    if latest and settings:
        warnings = generate_warnings(latest, settings)
        warning_status = get_warning_status(latest, settings)
        banner_text = warning_banner_text(latest, settings)
        analysis = analyze_temperature_trend(
            recent_rows,
            settings,
            interval_seconds=app.config.get("SENSOR_INTERVAL", 5),
        )
        display_status = get_display_status(latest, settings)
    else:
        warnings = []
        warning_status = {"has_warning": True}
        banner_text = "No data"
        analysis = {}
        display_status = {"text": "NO DATA"}

    chart_labels = [row["timestamp"] for row in recent_temp]
    chart_values = [row["temperature"] for row in recent_temp]
    return {
        "latest": latest_dict,
        "settings": settings_dict,
        "warnings": warnings,
        "analysis": analysis,
        "chart_labels": chart_labels,
        "chart_values": chart_values,
        "sensor_source": get_sensor_source_name(),
        "display_status": display_status,
        "runtime": runtime_state,
    }




# background woorker
def sensor_collection_worker(interval_seconds: int) -> None:
    """background sensor loop"""
    logger.info("Worker started interval=%ss", interval_seconds)
    runtime_state["collector_thread_alive"] = True

    while True:
        runtime_state["last_collection_attempt_at"] = safe_iso_now()

        try:
            success = collect_and_store_reading()


            if success:
                runtime_state["last_collection_success_at"] = safe_iso_now()
                runtime_state["consecutive_collection_failures"] = 0
                runtime_state["total_collection_successes"] += 1
                refresh_display_from_latest_data()

            else:
                runtime_state["consecutive_collection_failures"] += 1
                runtime_state["total_collection_failures"] += 1

        except Exception as exc:
            runtime_state["last_error"] = str(exc)
            logger.exception("Worker error: %s", exc)
            try:
                show_system_error("COLLECT ERR")
            except Exception:
                pass

        time.sleep(max(1, interval_seconds))





# start worker thread
def start_background_worker() -> threading.Thread:
    """start worker"""
    interval_seconds = int(app.config.get("SENSOR_INTERVAL", 5))

    worker = threading.Thread(
        target=sensor_collection_worker,
        kwargs={"interval_seconds": interval_seconds},
        daemon=True,
    )
    worker.start()
    runtime_state["collector_thread_alive"] = worker.is_alive()
    return worker

# login route
@app.route("/login", methods=["GET", "POST"])
def login():
    """login page"""
    if request.method == "GET":
        if is_logged_in():
            return redirect(url_for("dashboard"))
        return render_template("login.html")
    data = request.form or request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", "")).strip()
    result = build_login_result(username, password)

    if result["success"]:
        return redirect(url_for("dashboard"))
    return render_template("login.html", error=result["message"]), 401



# logout
@app.route("/logout")
@login_required
def logout():
    """logout"""
    logout_user()
    return redirect(url_for("login"))

# home
@app.route("/")
def home():
    """home redirect"""
    if is_logged_in():
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))
# dashboard page

@app.route("/dashboard")
@login_required
def dashboard():
    """dashboard page"""
    return render_template("index.html", username=get_current_username())



@app.route("/api/data")
@login_required
def api_data():
    """get data"""
    try:
        return build_success_response(**build_dashboard_payload())
    except Exception as exc:
        return build_error_response("Failed to load data", 500, error=str(exc))



# update settings
@app.route("/api/settings", methods=["POST"])
@login_required
def api_settings():
    """update settings"""
    data = request.get_json(silent=True) or {}

    try:
        values = validate_threshold_payload(data)
    except ValueError as exc:
        return build_error_response(str(exc))

    success = update_settings(
        values["temp_min"],
        values["temp_max"],
        values["humidity_min"],
        values["humidity_max"],
        values["pressure_min"],
        values["pressure_max"],
    )


    if not success:
        return build_error_response("Failed to update settings", 500)

    return build_success_response(message="Settings updated")


# simulate data
@app.route("/api/simulate", methods=["POST"])
@login_required
def api_simulate():
    """simulate sensor"""
    data = request.get_json(silent=True) or {}

    try:
        values = validate_simulation_payload(data)
    except ValueError as exc:
        return build_error_response(str(exc))

    insert_sensor_data(
        values["temperature"],
        values["humidity"],
        values["pressure"],
    )

    return build_success_response(message="Data inserted")


# health check
@app.route("/api/health")
def api_health():
    """health check"""
    return build_success_response(status="ok")


# startup
init_db()
show_startup_message()
start_background_worker()


# run
if __name__ == "__main__":
    app.run(
        host=app.config.get("HOST", "0.0.0.0"),
        port=app.config.get("PORT", 5000),
        debug=app.config.get("DEBUG", False),
    )