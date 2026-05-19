"""
Local fallback dashboard assembly (deprecated for production).

Used only when ``USE_AWS_BRAIN`` is false or ``LOCAL_FALLBACK_ON_AWS_ERROR`` is
enabled and API Gateway is unreachable. Analysis and warnings here duplicate
Lambda logic — AWS ``get_dashboard_data`` is authoritative in production.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from config import get_config
from legacy.display_service import get_display_status
from services.analysis_service import analyze_temperature_trend
from services.warnings_util import (
    generate_warnings,
    get_warning_status,
    warning_banner_text,
)
from sensor import runtime as rt
from sensor.reader import get_sensor_source_name

logger = logging.getLogger("smart_env_monitor.services.local_fallback")


def _normalise_sensor_list(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out = [item for item in raw if isinstance(item, dict)]
    out.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)
    return out


def _chart_from_sensor_list(sensor_list: List[Dict[str, Any]]) -> tuple[List[str], List[float]]:
    chron = list(reversed(sensor_list[-50:]))
    labels = [str(r.get("timestamp", "")) for r in chron]
    values: List[float] = []
    for r in chron:
        try:
            values.append(float(r["temperature"]))
        except (KeyError, TypeError, ValueError):
            continue
    return labels, values


def build_local_fallback_payload(
    app,
    *,
    sensor_list: Optional[List[Dict[str, Any]]] = None,
    settings_dict: Optional[Dict[str, Any]] = None,
    error_message: str = "AWS API unavailable.",
) -> Dict[str, Any]:
    """
    Build dashboard JSON using local analysis modules (Flask Brain fallback).

    Optionally reads SQLite cache when ``USE_SQLITE_CACHE`` is enabled.
    """
    cfg_class = app.config.get("CONFIG_CLASS", get_config())
    trend_window = int(app.config.get("TREND_WINDOW", getattr(cfg_class, "TREND_WINDOW", 5)))
    sensor_interval = int(app.config.get("SENSOR_INTERVAL", getattr(cfg_class, "SENSOR_INTERVAL", 5)))

    sensor_list = _normalise_sensor_list(sensor_list or [])

    if not sensor_list and getattr(cfg_class, "USE_SQLITE_CACHE", False):
        try:
            from legacy.database import get_recent_sensor_data

            rows = get_recent_sensor_data(limit=50)
            for row in rows:
                sensor_list.append(
                    {
                        "temperature": float(row["temperature"]),
                        "humidity": float(row["humidity"]),
                        "pressure": float(row["pressure"]),
                        "timestamp": str(row["timestamp"]),
                    }
                )
            sensor_list = _normalise_sensor_list(sensor_list)
        except Exception as exc:
            logger.debug("SQLite fallback read skipped: %s", exc)

    if not settings_dict:
        settings_dict = dict(getattr(cfg_class, "CLOUD_DEFAULT_SETTINGS", {}))
        try:
            from legacy.database import get_settings

            row = get_settings()
            if row:
                settings_dict = {
                    "temp_min": float(row["temp_min"]),
                    "temp_max": float(row["temp_max"]),
                    "humidity_min": float(row["humidity_min"]),
                    "humidity_max": float(row["humidity_max"]),
                    "pressure_min": float(row["pressure_min"]),
                    "pressure_max": float(row["pressure_max"]),
                }
        except Exception:
            pass

    latest_dict = sensor_list[0] if sensor_list else None
    chart_labels, chart_values = _chart_from_sensor_list(sensor_list)
    chron = list(reversed(sensor_list[-50:]))
    recent_for_trend = chron[-max(trend_window + 5, 10) :]

    if latest_dict and settings_dict:
        warnings = generate_warnings(latest_dict, settings_dict)
        warning_status = get_warning_status(latest_dict, settings_dict)
        banner_text = warning_banner_text(latest_dict, settings_dict)
        analysis = analyze_temperature_trend(
            recent_for_trend,
            settings_dict,
            interval_seconds=sensor_interval,
        )
        display_status = get_display_status(latest_dict, settings_dict)
    else:
        warnings = ["No sensor data available (local fallback)."]
        warning_status = {
            "has_warning": True,
            "count": 1,
            "messages": warnings,
            "level": "error",
        }
        banner_text = error_message
        analysis = {
            "spike_drop": "Analysis unavailable (local fallback).",
            "trend": "Analysis unavailable (local fallback).",
            "prediction": "Analysis unavailable (local fallback).",
        }
        display_status = {"text": "NO DATA"}

    return {
        "success": False,
        "source": "local_fallback",
        "fallback_used": True,
        "error_code": "AWS_API_UNAVAILABLE",
        "message": error_message,
        "sensor_data": sensor_list,
        "latest": latest_dict,
        "settings": settings_dict,
        "warnings": warnings,
        "warning_status": warning_status,
        "warning_banner": banner_text,
        "analysis": analysis,
        "chart_labels": chart_labels,
        "chart_values": chart_values,
        "sensor_source": get_sensor_source_name(),
        "display_status": display_status,
        "runtime": dict(rt.runtime_state),
        "cloud": {
            "last_fetch_ok": False,
            "sensor_points": len(sensor_list),
        },
    }
