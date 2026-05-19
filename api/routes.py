"""REST JSON routes under ``/api/*`` — thin proxies to AWS API Gateway (AWS Brain)."""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Dict

from flask import Blueprint, current_app, jsonify, request

from api.auth import (
    build_login_result,
    build_register_result,
    get_current_username,
    is_logged_in,
    logout_user,
)
from cloud.client import CloudAPIClient, CloudClientError
from config import get_config
from sensor import runtime as rt
from sensor.reader import get_sensor_source_name
from services.aws_proxy import aws_unavailable_error, build_aws_dashboard_response
from services.dashboard_service import build_dashboard_payload
from services.local_fallback import build_local_fallback_payload
from services.settings_normalize import normalize_settings_dict

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
                return jsonify({"success": False, "message": "Authentication required.", "source": "aws"}), 401
            from flask import redirect, url_for

            return redirect(url_for("pages.login"))
        return view_func(*args, **kwargs)

    return wrapper


def build_success_response(**payload):
    payload.setdefault("source", "aws")
    payload["success"] = True
    return jsonify(payload)


def build_error_response(message: str, status_code: int = 400, **extra):
    payload = {"success": False, "message": message, "source": extra.get("source", "aws")}
    payload.update(extra)
    return jsonify(payload), status_code


def _cloud() -> CloudAPIClient:
    return current_app.extensions["cloud_client"]


def _cfg():
    return current_app.config.get("CONFIG_CLASS", get_config())


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


def validate_ingest_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    values = validate_simulation_payload(data)
    cfg = _cfg()
    out: Dict[str, Any] = {
        "device_id": str(data.get("device_id") or getattr(cfg, "DEVICE_ID", "pi-001")),
        **values,
    }
    if data.get("timestamp"):
        out["timestamp"] = str(data["timestamp"])
    return out


@api_bp.route("/data")
@login_required
def api_data():
    """Proxy AWS GET /data — warnings and analysis come from Lambda."""
    cfg = _cfg()
    device_id = request.args.get("device_id") or getattr(cfg, "DEVICE_ID", None)

    if getattr(cfg, "USE_AWS_BRAIN", True):
        try:
            logger.info("[DEBUG] /api/data source=CLOUD (calling AWS GET /data) device_id=%s", device_id)
            payload = build_aws_dashboard_response(current_app, _cloud(), device_id=device_id)
            return jsonify(payload)
        except CloudClientError as exc:
            logger.warning("[DEBUG] /api/data AWS GET /data failed: %s", exc)
            if getattr(cfg, "LOCAL_FALLBACK_ON_AWS_ERROR", False):
                logger.warning("[DEBUG] /api/data source=LOCAL_FALLBACK (LOCAL_FALLBACK_ON_AWS_ERROR=1)")
                body = build_local_fallback_payload(current_app, error_message=str(exc))
                body["data_source"] = "LOCAL_FALLBACK"
                return jsonify(body), 503
            err = aws_unavailable_error(exc)
            err.update(
                {
                    "latest": None,
                    "settings": None,
                    "warnings": [],
                    "warning_status": {"has_warning": False, "count": 0, "messages": [], "level": "error"},
                    "warning_banner": str(exc),
                    "analysis": {
                        "spike_drop": "Unavailable — AWS API unreachable.",
                        "trend": "Unavailable — AWS API unreachable.",
                        "prediction": "Unavailable — AWS API unreachable.",
                    },
                    "chart_labels": [],
                    "chart_values": [],
                    "sensor_source": get_sensor_source_name(),
                    "runtime": dict(rt.runtime_state),
                }
            )
            return jsonify(err), 503

    logger.warning("[DEBUG] /api/data source=LOCAL_FALLBACK (USE_AWS_BRAIN=false)")
    payload = build_dashboard_payload(current_app, _cloud(), device_id=device_id)
    payload["data_source"] = "LOCAL_FALLBACK"
    status = 200 if payload.get("success", True) else 503
    return jsonify(payload), status


@api_bp.route("/ingest", methods=["POST"])
@login_required
def api_ingest():
    """Forward sensor JSON to AWS POST /ingest."""
    data = request.get_json(silent=True) or {}
    try:
        payload = validate_ingest_payload(data)
    except ValueError as exc:
        return build_error_response(str(exc))

    result = _cloud().post_ingest(payload)
    if not result.get("success", True):
        return build_error_response(
            result.get("message", "Cloud ingest rejected the reading."),
            502,
            error_code=result.get("error_code", "INGEST_FAILED"),
            source="aws",
            fallback_used=False,
        )
    return build_success_response(
        message=result.get("message", "Sensor reading sent to cloud ingest."),
        stored=result.get("stored"),
    )


@api_bp.route("/settings", methods=["GET", "POST"])
@login_required
def api_settings():
    cfg = _cfg()
    device_id = request.args.get("device_id") or getattr(cfg, "DEVICE_ID", "pi-001")

    if request.method == "GET":
        try:
            result = _cloud().get_settings(device_id=device_id)
        except CloudClientError as exc:
            logger.warning("Cloud settings GET failed: %s", exc)
            return build_error_response(
                str(exc),
                502,
                fallback_used=False,
                **exc.to_flask_extra(),
            )
        if not result.get("success", True):
            return build_error_response(
                result.get("message", "Cloud returned unsuccessful GET /settings"),
                502,
                upstream_json=result,
            )
        body = dict(result)
        body.setdefault("source", "aws")
        body["success"] = True
        if isinstance(body.get("settings"), dict):
            normalized = normalize_settings_dict(body["settings"])
            if normalized:
                body["settings"] = normalized
        return jsonify(body)

    data = request.get_json(silent=True) or {}
    try:
        values = validate_threshold_payload(data)
    except ValueError as exc:
        return build_error_response(str(exc))

    try:
        logger.info(
            "[DEBUG] DynamoDB settings proxy POST device_id:%s payload_keys=%s",
            device_id,
            list(values.keys()),
        )
        result = _cloud().post_settings(values, device_id=device_id)
    except CloudClientError as exc:
        logger.warning("Cloud settings POST failed: %s", exc)
        return build_error_response(str(exc), 502, fallback_used=False, **exc.to_flask_extra())

    if not result.get("success", True):
        return build_error_response(
            result.get("message", "Update failed"),
            502,
            upstream_json=result,
        )
    settings_out = result.get("settings")
    if isinstance(settings_out, dict):
        from sensor import runtime as rt

        normalized = normalize_settings_dict(settings_out)
        if normalized:
            settings_out = normalized
        rt.runtime_state["settings_cache"] = settings_out

    return build_success_response(
        message=result.get("message", "Settings updated"),
        settings=settings_out,
    )


@api_bp.route("/simulate", methods=["POST"])
@login_required
def api_simulate():
    """Manual reading upload — forwards to AWS POST /ingest (alias for /api/ingest)."""
    data = request.get_json(silent=True) or {}
    try:
        payload = validate_ingest_payload(data)
    except ValueError as exc:
        return build_error_response(str(exc))

    result = _cloud().post_ingest(payload)
    if not result.get("success", True):
        return build_error_response(
            result.get("message", "Cloud ingest rejected the reading."),
            502,
            error_code=result.get("error_code", "INGEST_FAILED"),
            source="aws",
            fallback_used=False,
        )
    return build_success_response(
        message=result.get("message", "Sensor reading sent to cloud ingest."),
        stored=result.get("stored"),
    )


@api_bp.route("/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    result = build_login_result(username, password)
    status = 200 if result.get("success") else 401
    return jsonify(result), status


@api_bp.route("/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    email = str(data.get("email", "")).strip()
    password = str(data.get("password", ""))
    result = build_register_result(username, email, password)
    status = 201 if result.get("success") else 400
    return jsonify(result), status


@api_bp.route("/health")
def api_health():
    cfg = _cfg()
    aws_health: Dict[str, Any] = {}
    cloud_ok = False
    try:
        aws_health = _cloud().fetch_health(timeout=5.0)
        cloud_ok = True
    except CloudClientError as exc:
        aws_health = aws_unavailable_error(exc)

    body = {
        "success": cloud_ok,
        "source": "aws" if cloud_ok else "aws",
        "fallback_used": False,
        "aws_health": aws_health,
        "sensor_source": get_sensor_source_name(),
        "worker_alive": rt.runtime_state.get("collector_thread_alive", False),
        "cloud_data_endpoint_reachable": _cloud().ping_data_endpoint(timeout=3.0),
        "aws_api_base": getattr(cfg, "AWS_API_BASE", ""),
        "use_aws_brain": getattr(cfg, "USE_AWS_BRAIN", True),
    }
    if not cloud_ok:
        body["error_code"] = aws_health.get("error_code", "AWS_API_UNAVAILABLE")
        body["message"] = aws_health.get("message", "AWS health check failed.")
    return jsonify(body), (200 if cloud_ok else 503)


@api_bp.route("/auth/status")
def api_auth_status():
    cfg = _cfg()
    return build_success_response(
        disable_auth=bool(getattr(cfg, "DISABLE_AUTH", False)),
        logged_in=is_logged_in(),
        username=get_current_username() if is_logged_in() else None,
        use_aws_brain=getattr(cfg, "USE_AWS_BRAIN", True),
    )


@api_bp.route("/logout", methods=["POST"])
def api_logout():
    try:
        logout_user()
    except Exception:
        pass
    return build_success_response(message="Logged out")
