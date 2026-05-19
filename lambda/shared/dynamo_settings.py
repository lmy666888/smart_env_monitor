"""
DynamoDB threshold settings (singleton row id = "global").

Shared by ``get_dashboard_data`` and ``settings_handler`` Lambdas.
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal
from typing import Any, Dict

import boto3

logger = logging.getLogger(__name__)

SETTINGS_TABLE_NAME = os.environ.get("SETTINGS_TABLE_NAME", "DeviceSettings")

DEFAULT_SETTINGS: Dict[str, float] = {
    "temp_min": 0,
    "temp_max": 40,
    "humidity_min": 20,
    "humidity_max": 80,
    "pressure_min": 980,
    "pressure_max": 1030,
}

_REQUIRED_FIELDS = (
    "temp_min",
    "temp_max",
    "humidity_min",
    "humidity_max",
    "pressure_min",
    "pressure_max",
)

_dynamodb = boto3.resource("dynamodb")


def decimal_to_native(obj: Any) -> Any:
    if isinstance(obj, list):
        return [decimal_to_native(v) for v in obj]
    if isinstance(obj, dict):
        return {k: decimal_to_native(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    return obj


def load_settings(table_name: str | None = None) -> Dict[str, float]:
    """Read settings from DynamoDB or return defaults."""
    name = table_name or SETTINGS_TABLE_NAME
    try:
        table = _dynamodb.Table(name)
        response = table.get_item(Key={"id": "global"})
        item = response.get("Item")
        if not item:
            logger.info("No settings row in %s; using defaults.", name)
            return dict(DEFAULT_SETTINGS)
        item.pop("id", None)
        return decimal_to_native(item)
    except Exception as exc:
        logger.exception("Failed to read settings from %s: %s", name, exc)
        return dict(DEFAULT_SETTINGS)


def validate_settings_payload(payload: Dict[str, Any]) -> Dict[str, Decimal]:
    """Validate POST body; raises ValueError on bad input."""
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


def save_settings(values: Dict[str, Decimal], table_name: str | None = None) -> None:
    name = table_name or SETTINGS_TABLE_NAME
    table = _dynamodb.Table(name)
    table.put_item(Item={"id": "global", **values})
