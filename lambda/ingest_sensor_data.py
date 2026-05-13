"""
Lambda: POST /ingest

Receives sensor data from a Raspberry Pi (or simulator) and writes it to the
sensor DynamoDB table.

Expected request body:
    {
        "device_id": "pi-001",
        "temperature": 26.5,
        "humidity": 62.0,
        "pressure": 1011.0,
        "timestamp": "2026-05-13T15:50:42.803254"  # optional, generated if missing
    }

Environment variables:
    SENSOR_TABLE_NAME   DynamoDB table to write into.
"""

import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SENSOR_TABLE_NAME = os.environ.get("SENSOR_TABLE_NAME", "SmartEnvSensorData")

_dynamodb = boto3.resource("dynamodb")


def _build_response(status_code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
        },
        "body": json.dumps(payload),
    }


def _parse_body(event: Dict[str, Any]) -> Dict[str, Any]:
    """Parse the request body whether it arrives as dict, string, or base64."""
    body = (event or {}).get("body")
    if body is None:
        return {}
    if isinstance(body, dict):
        return body
    try:
        return json.loads(body)
    except (TypeError, ValueError):
        return {}


def _validate_reading(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate the incoming sensor reading and coerce numeric fields to Decimal
    for DynamoDB.

    Raises ValueError if the payload is missing required fields or contains
    physically implausible values.
    """
    required = ("temperature", "humidity", "pressure")
    missing = [k for k in required if k not in payload]
    if missing:
        raise ValueError(f"Missing required field(s): {', '.join(missing)}")

    try:
        temperature = float(payload["temperature"])
        humidity = float(payload["humidity"])
        pressure = float(payload["pressure"])
    except (TypeError, ValueError) as exc:
        raise ValueError("temperature, humidity and pressure must be numeric.") from exc

    if not -50 <= temperature <= 100:
        raise ValueError("temperature is out of plausible range.")
    if not 0 <= humidity <= 100:
        raise ValueError("humidity must be between 0 and 100.")
    if not 300 <= pressure <= 1200:
        raise ValueError("pressure is out of plausible range.")

    device_id = str(payload.get("device_id") or "pi-001")
    timestamp = str(payload.get("timestamp") or datetime.now(timezone.utc).isoformat())

    return {
        "device_id": device_id,
        "timestamp": timestamp,
        "temperature": Decimal(str(round(temperature, 2))),
        "humidity": Decimal(str(round(humidity, 2))),
        "pressure": Decimal(str(round(pressure, 2))),
    }


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    logger.info("ingest_sensor_data invoked.")

    payload = _parse_body(event)

    try:
        item = _validate_reading(payload)
    except ValueError as exc:
        return _build_response(400, {"success": False, "message": str(exc)})

    try:
        table = _dynamodb.Table(SENSOR_TABLE_NAME)
        table.put_item(Item=item)
    except Exception as exc:
        logger.exception("Failed to write sensor reading: %s", exc)
        return _build_response(500, {"success": False, "message": "Database write failed."})

    return _build_response(201, {
        "success": True,
        "message": "Sensor reading stored.",
        "stored": {
            "device_id": item["device_id"],
            "timestamp": item["timestamp"],
        },
    })


if __name__ == "__main__":
    sample = {
        "body": json.dumps({
            "device_id": "pi-001",
            "temperature": 26.5,
            "humidity": 62.0,
            "pressure": 1011.0,
        }),
    }
    print(json.dumps(lambda_handler(sample, None), indent=2))
