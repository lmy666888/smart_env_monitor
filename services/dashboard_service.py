"""
Assemble the dashboard JSON payload from AWS /data plus local runtime metadata.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from cloud.client import CloudAPIClient, CloudClientError
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

logger = logging.getLogger("smart_env_monitor.services.dashboard")


def row_to_dict(row: Optional[Any]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    try:
        return dict(row)
    except Exception:
        return None


def _normalise_cloud_reading_list(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
    out.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)
    return out


def build_dashboard_payload(
    app,
    cloud_client: CloudAPIClient,
    device_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch live data from DynamoDB via API Gateway and merge analysis, warnings,
    and local collector runtime (sensor source, upload timestamps).
    """
    cfg_class = app.config.get("CONFIG_CLASS", get_config())
    trend_window = int(app.config.get("TREND_WINDOW", getattr(cfg_class, "TREND_WINDOW", 5)))
    sensor_interval = int(app.config.get("SENSOR_INTERVAL", getattr(cfg_class, "SENSOR_INTERVAL", 5)))

    cloud_raw: Dict[str, Any] = {}
    try:
        cloud_raw = cloud_client.fetch_dashboard_data(device_id=device_id)
        rt.mark_cloud_fetch(True)
    except CloudClientError as exc:
        logger.warning("Dashboard cloud fetch failed: %s", exc)
        rt.mark_cloud_fetch(False, str(exc))
        cloud_raw = {}

    sensor_list = _normalise_cloud_reading_list(cloud_raw.get("sensor_data"))
    settings_raw = cloud_raw.get("settings")
    settings_dict = row_to_dict(settings_raw) if isinstance(settings_raw, dict) else None
    if settings_dict:
        rt.runtime_state["settings_cache"] = settings_dict

    latest_dict = row_to_dict(sensor_list[0]) if sensor_list else None

    # Chart: chronological slice of recent temperatures
    chron = list(reversed(sensor_list[-50:]))
    chart_labels = [str(r.get("timestamp", "")) for r in chron]
    chart_values: List[float] = []
    for r in chron:
        try:
            chart_values.append(float(r["temperature"]))
        except (KeyError, TypeError, ValueError):
            continue

    recent_for_trend = chron[-max(trend_window + 5, 10) :]

    if latest_dict and settings_dict:
        try:
            warnings = generate_warnings(latest_dict, settings_dict)
        except Exception as exc:
            logger.warning("generate_warnings failed: %s", exc)
            warnings = []
        try:
            warning_status = get_warning_status(latest_dict, settings_dict)
        except Exception:
            warning_status = {"has_warning": False, "count": 0, "messages": [], "level": "normal"}
        try:
            banner_text = warning_banner_text(latest_dict, settings_dict)
        except Exception:
            banner_text = "Status unavailable."
        try:
            analysis = analyze_temperature_trend(
                recent_for_trend,
                settings_dict,
                interval_seconds=sensor_interval,
            )
        except Exception as exc:
            logger.warning("analyze_temperature_trend failed: %s", exc)
            analysis = {
                "spike_drop": "Analysis unavailable.",
                "trend": "Analysis unavailable.",
                "prediction": "Analysis unavailable.",
            }
        try:
            display_status = get_display_status(latest_dict, settings_dict)
        except Exception:
            display_status = {"text": "DISPLAY OFF"}
    else:
        warnings = []
        if not sensor_list:
            warnings = ["No cloud sensor data yet. Waiting for device uploads."]
        warning_status = {
            "has_warning": bool(warnings),
            "count": len(warnings),
            "messages": warnings,
            "level": "error" if not sensor_list else "normal",
        }
        banner_text = (
            "No readings in DynamoDB yet. Start the sensor collector to stream data."
            if not sensor_list
            else "Settings unavailable from cloud."
        )
        analysis = {
            "spike_drop": "No analysis available yet.",
            "trend": "No analysis available yet.",
            "prediction": "No analysis available yet.",
        }
        display_status = {"text": "NO DATA"}

    payload = {
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
            "data_url": getattr(cfg_class, "AWS_DATA_URL", ""),
            "ingest_url_configured": bool(getattr(cfg_class, "AWS_INGEST_URL", "")),
            "last_fetch_ok": rt.runtime_state.get("cloud_api_reachable"),
            "sensor_points": len(sensor_list),
        },
    }
    return payload
