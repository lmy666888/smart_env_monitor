"""Lambda GET /data — returns sensor readings, settings, warnings, and analysis."""

from __future__ import annotations

import json
import logging
import os
from decimal import Decimal
from typing import Any, Dict, List

import boto3
from boto3.dynamodb.conditions import Key

from shared.analysis_service import analyze_temperature_trend
from shared.dynamo_settings import load_settings
from shared.alert_service import maybe_send_warning_alert
from shared.warnings_util import (
    generate_warnings,
    get_warning_status,
    warning_banner_text,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SENSOR_TABLE_NAME = os.environ.get("SENSOR_TABLE_NAME", "SensorData")
SETTINGS_TABLE_NAME = os.environ.get("SETTINGS_TABLE_NAME", "DeviceSettings")
READING_LIMIT = int(os.environ.get("READING_LIMIT", "50"))
SENSOR_INTERVAL = int(os.environ.get("SENSOR_INTERVAL", "5"))

_dynamodb = boto3.resource("dynamodb")


def _decimal_to_native(obj: Any) -> Any:
    if isinstance(obj, list):
        return [_decimal_to_native(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _decimal_to_native(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    return obj


def _build_response(status_code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
        },
        "body": json.dumps(payload, default=str),
    }


def _load_recent_readings(device_id: str = "pi-001") -> List[Dict[str, Any]]:
    try:
        table = _dynamodb.Table(SENSOR_TABLE_NAME)
        try:
            response = table.query(
                KeyConditionExpression=Key("device_id").eq(device_id),
                ScanIndexForward=False,
                Limit=READING_LIMIT,
            )
            items = response.get("Items", [])
        except Exception:
            logger.warning("Query failed, falling back to Scan.")
            response = table.scan(Limit=READING_LIMIT)
            items = response.get("Items", [])

        readings = _decimal_to_native(items)
        readings.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        return readings
    except Exception as exc:
        logger.exception("Failed to read sensor data: %s", exc)
        return []


def _chart_from_readings(readings: List[Dict[str, Any]]) -> tuple[List[str], List[float]]:
    chron = list(reversed(readings[-50:]))
    labels = [str(r.get("timestamp", "")) for r in chron]
    values: List[float] = []
    for r in chron:
        try:
            values.append(float(r["temperature"]))
        except (KeyError, TypeError, ValueError):
            continue
    return labels, values


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    logger.info("get_dashboard_data invoked.")

    params = (event or {}).get("queryStringParameters") or {}
    device_id = params.get("device_id", "pi-001")

    sensor_data = _load_recent_readings(device_id=device_id)
    settings = load_settings(SETTINGS_TABLE_NAME, device_id=device_id)
    latest = sensor_data[0] if sensor_data else None
    chart_labels, chart_values = _chart_from_readings(sensor_data)
    chron = list(reversed(sensor_data[-50:]))

    if latest and settings:
        warnings = generate_warnings(latest, settings)
        warning_status = get_warning_status(latest, settings)
        warning_banner = warning_banner_text(latest, settings)
        analysis = analyze_temperature_trend(
            chron,
            settings,
            interval_seconds=SENSOR_INTERVAL,
        )
    else:
        warnings = []
        if not sensor_data:
            warnings = ["No cloud sensor data yet. Waiting for device uploads."]
        warning_status = {
            "has_warning": bool(warnings),
            "count": len(warnings),
            "messages": warnings,
            "level": "error" if not sensor_data else "normal",
        }
        warning_banner = (
            "No readings in DynamoDB yet. Start the sensor collector to stream data."
            if not sensor_data
            else "Settings unavailable from cloud."
        )
        analysis = {
            "spike_drop": "No analysis available yet.",
            "trend": "No analysis available yet.",
            "prediction": "No analysis available yet.",
        }

    sensor_backend = "unknown"
    if isinstance(latest, dict):
        sensor_backend = str(
            latest.get("source") or latest.get("sensor_source") or "unknown"
        )
        latest.setdefault("source", sensor_backend)

    # SNS email (non-blocking for dashboard response).
    if latest and isinstance(warning_status, dict):
        maybe_send_warning_alert(
            device_id=device_id,
            latest=latest,
            warnings=warnings if isinstance(warnings, list) else [],
            warning_status=warning_status,
        )

    logger.info(
        "get_dashboard_data device_id=%s sensor_backend=%s points=%s level=%s",
        device_id,
        sensor_backend,
        len(sensor_data),
        warning_status.get("level") if isinstance(warning_status, dict) else None,
    )

    return _build_response(
        200,
        {
            "success": True,
            "source": "aws_lambda",
            "analysis_source": "aws_lambda",
            "warnings_source": "aws_lambda",
            "settings_source": "aws_lambda",
            "sensor_data": sensor_data,
            "latest": latest,
            "sensor_backend": sensor_backend,
            "settings": settings,
            "warnings": warnings,
            "warning_status": warning_status,
            "warning_banner": warning_banner,
            "analysis": analysis,
            "chart_labels": chart_labels,
            "chart_values": chart_values,
        },
    )


if __name__ == "__main__":
    print(json.dumps(lambda_handler({}, None), indent=2))
