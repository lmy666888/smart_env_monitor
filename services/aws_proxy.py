"""
AWS Brain proxy: pass through GET /data from API Gateway with minimal Flask metadata.

Warnings, trend analysis, spike detection, and predictions must come from Lambda
(``get_dashboard_data``). This module only adds presentation fields (charts)
and local runtime indicators (sensor source, upload worker).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from cloud.client import CloudAPIClient, CloudClientError
from config import get_config
from legacy.display_service import get_display_status
from sensor import runtime as rt
from sensor.reader import get_sensor_source_name

logger = logging.getLogger("smart_env_monitor.services.aws_proxy")


def _normalise_sensor_list(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out = [item for item in raw if isinstance(item, dict)]
    out.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)
    return out


def _ensure_chart_fields(payload: Dict[str, Any], sensor_list: List[Dict[str, Any]]) -> None:
    """Derive chart series from sensor_data when AWS omitted them (presentation only)."""
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


def _merge_runtime_metadata(payload: Dict[str, Any], cfg_class: type) -> None:
    payload.setdefault("sensor_source", get_sensor_source_name())
    payload.setdefault("runtime", dict(rt.runtime_state))
    payload.setdefault(
        "cloud",
        {
            "data_url": getattr(cfg_class, "AWS_DATA_URL", ""),
            "ingest_url_configured": bool(getattr(cfg_class, "AWS_INGEST_URL", "")),
            "last_fetch_ok": rt.runtime_state.get("cloud_api_reachable"),
            "sensor_points": len(_normalise_sensor_list(payload.get("sensor_data"))),
        },
    )
    latest = payload.get("latest")
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
    """
    Fetch GET /data from AWS and return payload unchanged for brain fields.

    Does not recompute warnings, warning_status, or analysis when AWS provides them.
    """
    cfg_class = app.config.get("CONFIG_CLASS", get_config())

    cloud_raw = cloud_client.fetch_dashboard_data(device_id=device_id)
    rt.mark_cloud_fetch(True)

    payload: Dict[str, Any] = dict(cloud_raw)
    payload["success"] = bool(payload.get("success", True))
    payload["source"] = "aws"
    payload["fallback_used"] = False

    sensor_list = _normalise_sensor_list(payload.get("sensor_data"))
    payload["sensor_data"] = sensor_list

    if payload.get("latest") is None and sensor_list:
        payload["latest"] = sensor_list[0]

    settings = payload.get("settings")
    if isinstance(settings, dict):
        rt.runtime_state["settings_cache"] = settings

    _ensure_chart_fields(payload, sensor_list)
    _merge_runtime_metadata(payload, cfg_class)

    return payload


def aws_unavailable_error(exc: CloudClientError) -> Dict[str, Any]:
    """Standard error envelope when AWS Brain cannot be reached."""
    return {
        "success": False,
        "source": "aws",
        "fallback_used": False,
        "error_code": exc.error_code or "AWS_API_UNAVAILABLE",
        "message": str(exc),
        "upstream_http_status": exc.status_code,
        "upstream_url": exc.url,
    }
