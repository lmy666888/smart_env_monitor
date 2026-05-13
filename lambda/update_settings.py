"""
Lambda: POST /settings

Updates the singleton threshold settings row used by the dashboard for
warning evaluation.

Expected request body (all fields required, all numeric):
    {
        "temp_min": 0,
        "temp_max": 40,
        "humidity_min": 20,
        "humidity_max": 80,
        "pressure_min": 980,
        "pressure_max": 1030
    }

Environment variables:
    SETTINGS_TABLE_NAME  DynamoDB table that stores the singleton settings row.
"""

import json
import logging
import os
from decimal import Decimal
from typing import Any, Dict

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SETTINGS_TABLE_NAME = os.environ.get("SETTINGS_TABLE_NAME", "SmartEnvSettings")

_REQUIRED_FIELDS = (
    "temp_min", "temp_max",
    "humidity_min", "humidity_max",
    "pressure_min", "pressure_max",
)

_dynamodb = boto3.resource("dynamodb")


def _build_response(status_code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(payload),
    }


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


def _validate(payload: Dict[str, Any]) -> Dict[str, Decimal]:
    """
    Coerce each setting to Decimal and ensure min < max for every pair.
    Raises ValueError on bad input.
    """
    missing = [k for k in _REQUIRED_FIELDS if k not in payload]
    if missing:
        raise ValueError(f"Missing required field(s): {', '.join(missing)}")

    try:
        values: Dict[str, Decimal] = {}
        for key in _REQUIRED_FIELDS:
            values[key] = Decimal(str(float(payload[key])))
    except (TypeError, ValueError) as exc:
        raise ValueError("All threshold values must be numeric.") from exc

    pairs = (
        ("temp_min", "temp_max", "Temperature"),
        ("humidity_min", "humidity_max", "Humidity"),
        ("pressure_min", "pressure_max", "Pressure"),
    )
    for min_key, max_key, label in pairs:
        if values[min_key] >= values[max_key]:
            raise ValueError(f"{label} minimum must be less than maximum.")

    return values


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    logger.info("update_settings invoked.")
    payload = _parse_body(event)

    try:
        values = _validate(payload)
    except ValueError as exc:
        return _build_response(400, {"success": False, "message": str(exc)})

    item = {"id": "global", **values}

    try:
        table = _dynamodb.Table(SETTINGS_TABLE_NAME)
        table.put_item(Item=item)
    except Exception as exc:
        logger.exception("Failed to write settings: %s", exc)
        return _build_response(500, {"success": False, "message": "Database write failed."})

    return _build_response(200, {
        "success": True,
        "message": "Settings updated.",
        "settings": {k: float(v) for k, v in values.items()},
    })


if __name__ == "__main__":
    sample = {
        "body": json.dumps({
            "temp_min": 0, "temp_max": 40,
            "humidity_min": 20, "humidity_max": 80,
            "pressure_min": 980, "pressure_max": 1030,
        }),
    }
    print(json.dumps(lambda_handler(sample, None), indent=2))
