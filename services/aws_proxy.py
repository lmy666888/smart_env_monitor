"""
AWS Brain proxy: pass through GET /data from API Gateway with minimal Flask metadata.

Warnings, trend analysis, spike detection, and predictions come from Lambda
``get_dashboard_data`` when present; otherwise computed via ``lambda/shared``
(same code path as Lambda, NOT ``services/analysis_service``).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from cloud.client import CloudAPIClient, CloudClientError
from config import get_config
from legacy.display_service import get_display_status
from sensor import runtime as rt
from sensor.reader import get_sensor_source_name
from services.cloud_brain import cloud_payload_has_brain_fields, enrich_cloud_dashboard_payload
from services.settings_normalize import normalize_settings_dict

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


def _resolve_cloud_sensor_backend(payload: Dict[str, Any]) -> str:
    """Latest reading source from DynamoDB (via Lambda), not local Flask reader."""
    backend = payload.get("sensor_backend")
    if backend:
        return str(backend)
    latest = payload.get("latest")
    if isinstance(latest, dict):
        return str(latest.get("source") or latest.get("sensor_source") or "unknown")
    return "unknown"


def _apply_sensor_source_metadata(payload: Dict[str, Any]) -> None:
    """
    CLOUD mode: preserve AWS ``sensor_backend`` / ``latest.source``.
    Local mode: use Flask ``get_sensor_source_name()``.
    """
    is_cloud = payload.get("data_source") == "CLOUD" or payload.get("source") == "aws"
    if is_cloud:
        backend = _resolve_cloud_sensor_backend(payload)
        payload["sensor_backend"] = backend
        payload["sensor_source"] = backend
        latest = payload.get("latest")
        if isinstance(latest, dict) and backend != "unknown":
            latest.setdefault("source", backend)
        logger.info(
            "[DEBUG] /api/data returning sensor_backend=%s latest.source=%s",
            backend,
            (latest or {}).get("source") if isinstance(latest, dict) else None,
        )
    else:
        local_src = get_sensor_source_name()
        payload.setdefault("sensor_source", local_src)
        payload.setdefault("sensor_backend", local_src)


def _merge_runtime_metadata(payload: Dict[str, Any], cfg_class: type) -> None:
    _apply_sensor_source_metadata(payload)
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
    latest = payload.get("latest")
    settings = payload.get("settings")
    if latest and settings and "display_status" not in payload:
        try:
            payload["display_status"] = get_display_status(latest, settings)
        except Exception:
            payload["display_status"] = {"text": "DISPLAY OFF"}


def _log_dashboard_debug(
    payload: Dict[str, Any],
    *,
    cloud_raw_keys: List[str],
    device_id: Optional[str],
) -> None:
    """Structured debug line for verifying CLOUD vs backfill path."""
    settings = payload.get("settings") or {}
    analysis = payload.get("analysis") or {}
    warnings = payload.get("warnings") or []
    logger.info(
        "[DEBUG] /api/data source=CLOUD device_id=%s aws_keys=%s "
        "settings_source=%s analysis_source=%s warnings_source=%s "
        "settings=%s latest.temp=%s warnings=%s analysis=%s",
        device_id or "—",
        cloud_raw_keys,
        payload.get("settings_source", "?"),
        payload.get("analysis_source", "?"),
        payload.get("warnings_source", "?"),
        {k: settings.get(k) for k in ("temp_min", "temp_max", "humidity_min", "humidity_max")},
        (payload.get("latest") or {}).get("temperature"),
        warnings,
        {k: analysis.get(k) for k in ("spike_drop", "trend", "prediction")},
    )
    if getattr(get_config(), "DEBUG", False):
        logger.debug(
            "[DEBUG] full AWS /data payload snapshot: %s",
            json.dumps(
                {
                    "settings": payload.get("settings"),
                    "warnings": warnings,
                    "warning_status": payload.get("warning_status"),
                    "analysis": analysis,
                },
                default=str,
            )[:2000],
        )


def build_aws_dashboard_response(
    app,
    cloud_client: CloudAPIClient,
    device_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch GET /data from AWS; enrich with lambda/shared brain fields when needed.
    """
    cfg_class = app.config.get("CONFIG_CLASS", get_config())
    sensor_interval = int(
        app.config.get("SENSOR_INTERVAL", getattr(cfg_class, "SENSOR_INTERVAL", 5))
    )

    cloud_raw = cloud_client.fetch_dashboard_data(device_id=device_id)
    rt.mark_cloud_fetch(True)

    cloud_raw_keys = list(cloud_raw.keys()) if isinstance(cloud_raw, dict) else []
    had_brain_on_wire = cloud_payload_has_brain_fields(cloud_raw) if isinstance(cloud_raw, dict) else False

    payload: Dict[str, Any] = dict(cloud_raw)
    payload["success"] = bool(payload.get("success", True))
    payload["source"] = "aws"
    payload["fallback_used"] = False
    payload["data_source"] = "CLOUD"

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
        else:
            rt.runtime_state["settings_cache"] = settings

    # Recompute brain fields when Lambda response is legacy/minimal or settings stale.
    force_recompute = not had_brain_on_wire or payload.get("settings_source") == "settings_cache_merge"
    enrich_cloud_dashboard_payload(
        payload,
        settings_cache=rt.runtime_state.get("settings_cache"),
        sensor_interval=sensor_interval,
        force_recompute=not had_brain_on_wire,
    )

    if had_brain_on_wire and payload.get("settings_source") != "settings_cache_merge":
        payload.setdefault("analysis_source", "aws_lambda")
        payload.setdefault("warnings_source", "aws_lambda")
        payload.setdefault("settings_source", "aws_lambda")

    _ensure_chart_fields(payload, sensor_list)
    _merge_runtime_metadata(payload, cfg_class)

    _log_dashboard_debug(payload, cloud_raw_keys=cloud_raw_keys, device_id=device_id)

    return payload


def aws_unavailable_error(exc: CloudClientError) -> Dict[str, Any]:
    """Standard error envelope when AWS Brain cannot be reached."""
    return {
        "success": False,
        "source": "aws",
        "data_source": "AWS_ERROR",
        "fallback_used": False,
        "error_code": exc.error_code or "AWS_API_UNAVAILABLE",
        "message": str(exc),
        "upstream_http_status": exc.status_code,
        "upstream_url": exc.url,
    }
