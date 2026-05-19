"""
Lambda: POST /simulate (or scheduled EventBridge trigger)

Generates one synthetic sensor reading and stores it via the same code path
used by ingest_sensor_data. Useful for demos when no real Pi is attached.

Environment variables:
    SENSOR_TABLE_NAME   DynamoDB table to write into.
    SIM_DEVICE_ID       Device id to tag generated readings with (default pi-sim-001).
"""

import json
import logging
import os
import random
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SENSOR_TABLE_NAME = os.environ.get("SENSOR_TABLE_NAME", "SensorData")
SIM_DEVICE_ID = os.environ.get("SIM_DEVICE_ID", "pi-sim-001")

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


def _generate_reading(seed: float | None = None) -> Dict[str, Any]:
    """
    Generate a plausible single reading.

    seed: an optional center temperature; small noise is added so charts move.
    """
    base_temp = seed if seed is not None else 24.0
    temperature = round(base_temp + random.uniform(-1.5, 1.5), 2)
    humidity = round(random.uniform(40, 70), 2)
    pressure = round(random.uniform(1005, 1020), 2)

    return {
        "device_id": SIM_DEVICE_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temperature": Decimal(str(temperature)),
        "humidity": Decimal(str(humidity)),
        "pressure": Decimal(str(pressure)),
    }


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    logger.info("simulate_sensor_data invoked.")

    # Allow callers to nudge the base temperature for demo scenarios.
    base_temp = None
    if isinstance(event, dict):
        body = event.get("body")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except (TypeError, ValueError):
                body = {}
        if isinstance(body, dict) and "temperature" in body:
            try:
                base_temp = float(body["temperature"])
            except (TypeError, ValueError):
                base_temp = None

    item = _generate_reading(seed=base_temp)

    try:
        table = _dynamodb.Table(SENSOR_TABLE_NAME)
        table.put_item(Item=item)
    except Exception as exc:
        logger.exception("Failed to store simulated reading: %s", exc)
        return _build_response(500, {"success": False, "message": "Database write failed."})

    return _build_response(201, {
        "success": True,
        "message": "Simulated reading stored.",
        "stored": {
            "device_id": item["device_id"],
            "timestamp": item["timestamp"],
            "temperature": float(item["temperature"]),
            "humidity": float(item["humidity"]),
            "pressure": float(item["pressure"]),
        },
    })


if __name__ == "__main__":
    print(json.dumps(lambda_handler({}, None), indent=2))
