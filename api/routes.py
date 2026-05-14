"""REST JSON routes under ``/api/*``."""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Dict

from flask import Blueprint, current_app, jsonify, request

from api.auth import build_login_result, get_current_username, is_logged_in, logout_user
from cloud.client import CloudAPIClient, CloudClientError
from config import get_config
from sensor import runtime as rt
from sensor.reader import get_sensor_source_name
from services.dashboard_service import build_dashboard_payload

logger = logging.getLogger("smart_env_monitor.api.routes")

api_bp = Blueprint("api", __name__, url_prefix="/api")


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        cfg = current_app.config.get("CONFIG_CLASS", get_config())
        if getattr(cfg, "DISABLE_AUTH", False):
            return view_func(*args, **kwargs)
        if not is_logged_in():
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "message": "Authentication required."}), 401
            from flask import redirect, url_for

            return redirect(url_for("pages.login"))
        return view_func(*args, **kwargs)

    return wrapper


def build_success_response(**payload):
    payload["success"] = True
    return jsonify(payload)


def build_error_response(message: str, status_code: int = 400, **extra):
    payload = {"success": False, "message": message}
    payload.update(extra)
    return jsonify(payload), status_code


def _cloud() -> CloudAPIClient:
    return current_app.extensions["cloud_client"]


def validate_threshold_payload(data: Dict[str, Any]) -> Dict[str, float]:
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


def validate_simulation_payload(data: Dict[str, Any]) -> Dict[str, float]:
    try:
        return {
            "temperature": float(data["temperature"]),
            "humidity": float(data["humidity"]),
            "pressure": float(data["pressure"]),
        }
    except (KeyError, TypeError, ValueError):
        raise ValueError("Invalid sensor values.")


@api_bp.route("/data")
@login_required
def api_data():
    try:
        payload = build_dashboard_payload(current_app, _cloud())
        return build_success_response(**payload)
    except Exception as exc:
        logger.warning("api_data fallback: %s", exc)
        cfg = current_app.config.get("CONFIG_CLASS", get_config())
        return jsonify(
            {
                "success": True,
                "latest": None,
                "settings": None,
                "warnings": [],
                "warning_status": {
                    "has_warning": False,
                    "count": 0,
                    "messages": [],
                    "level": "normal",
                },
                "warning_banner": "Dashboard data temporarily unavailable.",
                "analysis": {
                    "spike_drop": "No analysis available.",
                    "trend": "No analysis available.",
                    "prediction": "No analysis available.",
                },
                "chart_labels": [],
                "chart_values": [],
                "sensor_source": get_sensor_source_name(),
                "display_status": {"text": "ERROR"},
                "runtime": dict(rt.runtime_state),
                "cloud": {"error": str(exc)},
                "error": str(exc),
            }
        )


@api_bp.route("/settings", methods=["GET", "POST"])
@login_required
def api_settings():
    if request.method == "GET":
        try:
            result = _cloud().get_settings()
        except CloudClientError as exc:
            logger.warning("Cloud settings GET failed: %s", exc)
            return build_error_response(
                str(exc),
                502,
                **exc.to_flask_extra(),
            )
        if not result.get("success", True):
            return build_error_response(
                result.get("message", "Cloud returned unsuccessful GET /settings"),
                502,
                upstream_json=result,
            )
        return build_success_response(settings=result.get("settings"))

    data = request.get_json(silent=True) or {}
    try:
        values = validate_threshold_payload(data)
    except ValueError as exc:
        return build_error_response(str(exc))

    try:
        result = _cloud().post_settings(values)
    except CloudClientError as exc:
        logger.warning("Cloud settings POST failed: %s", exc)
        return build_error_response(
            str(exc),
            502,
            **exc.to_flask_extra(),
        )

    if not result.get("success", True):
        return build_error_response(
            result.get("message", "Update failed"),
            502,
            upstream_json=result,
        )
    return build_success_response(
        message=result.get("message", "Settings updated"),
        settings=result.get("settings"),
    )


@api_bp.route("/simulate", methods=["POST"])
@login_required
def api_simulate():
    data = request.get_json(silent=True) or {}
    try:
        values = validate_simulation_payload(data)
    except ValueError as exc:
        return build_error_response(str(exc))

    cfg = current_app.config.get("CONFIG_CLASS", get_config())
    payload = {
        "device_id": getattr(cfg, "DEVICE_ID", "pi-001"),
        "temperature": values["temperature"],
        "humidity": values["humidity"],
        "pressure": values["pressure"],
    }
    ok = _cloud().post_sensor_reading(payload)
    if not ok:
        return build_error_response("Cloud ingest rejected the reading.", 502)
    return build_success_response(message="Sensor reading sent to cloud ingest.")


@api_bp.route("/health")
def api_health():
    cfg = current_app.config.get("CONFIG_CLASS", get_config())
    cloud_ok = _cloud().ping_data_endpoint(timeout=3.0)
    return build_success_response(
        status="ok",
        sensor_source=get_sensor_source_name(),
        worker_alive=rt.runtime_state.get("collector_thread_alive", False),
        cloud_data_endpoint_reachable=cloud_ok,
        aws_api_base=getattr(cfg, "AWS_API_BASE", ""),
    )


@api_bp.route("/auth/status")
def api_auth_status():
    cfg = current_app.config.get("CONFIG_CLASS", get_config())
    return build_success_response(
        disable_auth=bool(getattr(cfg, "DISABLE_AUTH", False)),
        logged_in=is_logged_in(),
        username=get_current_username() if is_logged_in() else None,
    )


@api_bp.route("/logout", methods=["POST"])
def api_logout():
    try:
        logout_user()
    except Exception:
        pass
    return build_success_response(message="Logged out")
