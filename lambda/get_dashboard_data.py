"""
Lambda: GET /data

Returns the dashboard payload consumed by the frontend:

    {
        "sensor_data": [
            {
                "device_id": "pi-001",
                "humidity": 62.0,
                "pressure": 1011.0,
                "temperature": 26.5,
                "timestamp": "2026-05-13T15:50:42.803254"
            },
            ...
        ],
        "settings": {
            "temp_min": 0,
            "temp_max": 40,
            "humidity_min": 20,
            "humidity_max": 80,
            "pressure_min": 980,
            "pressure_max": 1030
        }
    }

Environment variables:
    SENSOR_TABLE_NAME    DynamoDB table that stores sensor readings.
                         (partition key: device_id, sort key: timestamp)
    SETTINGS_TABLE_NAME  DynamoDB table that stores the singleton settings row.
                         (partition key: id, value = "global")
    READING_LIMIT        Optional, defaults to 50.
"""

import json
import logging
import os
from decimal import Decimal
from typing import Any, Dict, List

import boto3
from boto3.dynamodb.conditions import Key

from shared.dynamo_settings import load_settings

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SENSOR_TABLE_NAME = os.environ.get("SENSOR_TABLE_NAME", "SmartEnvSensorData")
SETTINGS_TABLE_NAME = os.environ.get("SETTINGS_TABLE_NAME", "SmartEnvSettings")
READING_LIMIT = int(os.environ.get("READING_LIMIT", "50"))

_dynamodb = boto3.resource("dynamodb")


def _decimal_to_native(obj: Any) -> Any:
    """Convert DynamoDB Decimal values to plain int/float for JSON serialization."""
    if isinstance(obj, list):
        return [_decimal_to_native(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _decimal_to_native(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        # Integral decimals -> int; otherwise -> float.
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    return obj


def _build_response(status_code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Standard API Gateway HTTP API response with CORS headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
        },
        "body": json.dumps(payload, default=str),
    }


def _load_settings() -> Dict[str, float]:
    """Load threshold settings from DynamoDB, falling back to defaults."""
    return load_settings(SETTINGS_TABLE_NAME)


def _load_recent_readings(device_id: str = "pi-001") -> List[Dict[str, Any]]:
    """
    Load the most recent sensor readings for a device, newest first.

    Falls back to a Scan if the device_id query fails (e.g. table missing
    a sort key). Result count is capped by READING_LIMIT.
    """
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
        # Sort newest first by timestamp, matching the existing API contract.
        readings.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        return readings
    except Exception as exc:
        logger.exception("Failed to read sensor data: %s", exc)
        return []


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """API Gateway entry point."""
    logger.info("get_dashboard_data invoked.")

    # Optional ?device_id=... support.
    params = (event or {}).get("queryStringParameters") or {}
    device_id = params.get("device_id", "pi-001")

    sensor_data = _load_recent_readings(device_id=device_id)
    settings = _load_settings()

    return _build_response(200, {
        "sensor_data": sensor_data,
        "settings": settings,
    })


if __name__ == "__main__":
    # Local smoke test.
    print(json.dumps(lambda_handler({}, None), indent=2))
