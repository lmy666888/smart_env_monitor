"""Proxy GET /data from API Gateway — no local brain recompute (Lambda only)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from cloud.client import CloudAPIClient, CloudClientError
from legacy.display_service import get_display_status
from sensor import runtime as rt
from services.settings_normalize import normalize_settings_dict

logger = logging.getLogger("smart_env_monitor.services.aws_proxy")


def _normalise_sensor_list(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out = [item for item in raw if isinstance(item, dict)]
    out.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)
    return out


def _ensure_chart_fields(payload: Dict[str, Any], sensor_list: List[Dict[str, Any]]) -> None:
    """Chart series from sensor_data only (UI presentation, not analysis)."""
    if payload.get("chart_labels") and payload.get("chart_values"):
        return
    chron = list(reversed(sensor_list[-50:]))
    payload.setdefault("chart_labels", [str(r.get("timestamp", "")) for r in chron])
    values: List[float] = []
    for r in chron:
        try:
            values.append(float(r["temperature"]))
        except (KeyError, TypeError, ValueError):
            continue
    payload.setdefault("chart_values", values)


def _resolve_cloud_sensor_backend(payload: Dict[str, Any]) -> str:
    backend = payload.get("sensor_backend")
    if backend:
        return str(backend)
    latest = payload.get("latest")
    if isinstance(latest, dict):
        return str(latest.get("source") or latest.get("sensor_source") or "unknown")
    return "unknown"


def _merge_runtime_metadata(payload: Dict[str, Any], cfg_class: type) -> None:
    backend = _resolve_cloud_sensor_backend(payload)
    payload["sensor_backend"] = backend
    payload["sensor_source"] = backend
    latest = payload.get("latest")
    if isinstance(latest, dict) and backend != "unknown":
        latest.setdefault("source", backend)

    payload.setdefault("runtime", dict(rt.runtime_state))
    payload.setdefault(
        "cloud",
        {
            "data_url": getattr(cfg_class, "AWS_DATA_URL", ""),
            "ingest_url_configured": bool(getattr(cfg_class, "AWS_INGEST_URL", "")),
            "last_fetch_ok": rt.runtime_state.get("cloud_api_reachable"),
            "sensor_points": len(_normalise_sensor_list(payload.get("sensor_data"))),
            "data_source": "CLOUD",
        },
    )
    settings = payload.get("settings")
    if latest and settings and "display_status" not in payload:
        try:
            payload["display_status"] = get_display_status(latest, settings)
        except Exception:
            payload["display_status"] = {"text": "DISPLAY OFF"}


def build_aws_dashboard_response(
    app,
    cloud_client: CloudAPIClient,
    device_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch GET /data from Lambda and pass through (BFF only)."""
    cfg_class = app.config.get("CONFIG_CLASS")

    cloud_raw = cloud_client.fetch_dashboard_data(device_id=device_id)
    rt.mark_cloud_fetch(True)

    payload: Dict[str, Any] = dict(cloud_raw)
    payload["success"] = bool(payload.get("success", True))
    payload["fallback_used"] = False
    payload["data_source"] = "CLOUD"
    payload["source"] = payload.get("source") or "aws"
    payload["analysis_source"] = "aws_lambda"
    payload["warnings_source"] = "aws_lambda"
    payload["settings_source"] = "aws_lambda"

    sensor_list = _normalise_sensor_list(payload.get("sensor_data"))
    payload["sensor_data"] = sensor_list

    if payload.get("latest") is None and sensor_list:
        payload["latest"] = sensor_list[0]

    settings = payload.get("settings")
    if isinstance(settings, dict):
        normalized = normalize_settings_dict(settings)
        if normalized:
            payload["settings"] = normalized
            rt.runtime_state["settings_cache"] = normalized

    _ensure_chart_fields(payload, sensor_list)
    _merge_runtime_metadata(payload, cfg_class)

    logger.info(
        "BFF /api/data proxied from Lambda device_id=%s points=%s level=%s",
        device_id or "—",
        len(sensor_list),
        (payload.get("warning_status") or {}).get("level"),
    )

    return payload


def aws_unavailable_error(exc: CloudClientError) -> Dict[str, Any]:
    return {
        "success": False,
        "source": "aws",
        "data_source": "AWS_ERROR",
        "fallback_used": False,
        "analysis_source": "aws_lambda",
        "warnings_source": "aws_lambda",
        "settings_source": "aws_lambda",
        "error_code": exc.error_code or "AWS_API_UNAVAILABLE",
        "message": str(exc),
        "upstream_http_status": exc.status_code,
        "upstream_url": exc.url,
    }
