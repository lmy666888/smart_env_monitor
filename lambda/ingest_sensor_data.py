"""Lambda POST /ingest — validate sensor readings, check device key, write to DynamoDB."""

import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SENSOR_TABLE_NAME = os.environ.get("SENSOR_TABLE_NAME", "SensorData")
DEVICE_API_KEY = os.environ.get("DEVICE_API_KEY", "").strip()

_dynamodb = boto3.resource("dynamodb")


def _build_response(status_code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,X-DEVICE-KEY",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
        },
        "body": json.dumps(payload),
    }


def _header_lookup(event: Dict[str, Any], name: str) -> Optional[str]:
    headers = (event or {}).get("headers") or {}
    if not isinstance(headers, dict):
        return None
    target = name.lower()
    for key, value in headers.items():
        if str(key).lower() == target:
            return str(value) if value is not None else None
    return None


def _verify_device_key(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not DEVICE_API_KEY:
        return None
    provided = (_header_lookup(event, "X-DEVICE-KEY") or "").strip()
    if provided != DEVICE_API_KEY:
        logger.warning("Ingest rejected: invalid or missing X-DEVICE-KEY.")
        return _build_response(
            403,
            {
                "success": False,
                "message": "Forbidden: invalid device API key.",
                "error_code": "DEVICE_KEY_FORBIDDEN",
            },
        )
    return None


def _parse_body(event: Dict[str, Any]) -> Dict[str, Any]:
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

    if not -40 <= temperature <= 100:
        raise ValueError("temperature is out of plausible range (-40 to 100).")
    if not 0 <= humidity <= 100:
        raise ValueError("humidity must be between 0 and 100.")
    if not 800 <= pressure <= 1200:
        raise ValueError("pressure is out of plausible range (800 to 1200).")

    device_id = str(payload.get("device_id") or "pi-001")
    timestamp = str(payload.get("timestamp") or datetime.now(timezone.utc).isoformat())
    source = str(payload.get("source") or payload.get("sensor_source") or "").strip()
    if not source:
        source = "unknown"

    item = {
        "device_id": device_id,
        "timestamp": timestamp,
        "temperature": Decimal(str(round(temperature, 2))),
        "humidity": Decimal(str(round(humidity, 2))),
        "pressure": Decimal(str(round(pressure, 2))),
        "source": source,
    }
    return item


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    logger.info("ingest_sensor_data invoked.")

    denied = _verify_device_key(event)
    if denied is not None:
        return denied

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

    logger.info(
        "Stored reading device_id=%s source=%s T=%s H=%s P=%s",
        item["device_id"],
        item.get("source"),
        item["temperature"],
        item["humidity"],
        item["pressure"],
    )
    return _build_response(201, {
        "success": True,
        "message": "Sensor reading stored.",
        "stored": {
            "device_id": item["device_id"],
            "timestamp": item["timestamp"],
            "source": item.get("source"),
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
