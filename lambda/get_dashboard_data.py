"""
Lambda: GET /data (AWS Brain — authoritative dashboard payload)

Returns sensor history, settings, warnings, warning_status, analysis, and chart
series. Flask proxies this response without recomputing analysis.

Environment variables:
    SENSOR_TABLE_NAME     DynamoDB SensorData (partition: device_id, sort: timestamp)
    SETTINGS_TABLE_NAME   DynamoDB DeviceSettings (partition key: device_id, e.g. pi-001)
    READING_LIMIT         Optional, default 50
    SENSOR_INTERVAL       Optional, seconds between readings for prediction text
"""

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
    logger.info("get_dashboard_data invoked (AWS Brain).")

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

    return _build_response(
        200,
        {
            "success": True,
            "source": "aws",
            "sensor_data": sensor_data,
            "latest": latest,
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
