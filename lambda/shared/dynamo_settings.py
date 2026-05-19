"""
DynamoDB threshold settings — one row per device.

Canonical schema (DeviceSettings table):
    Partition key: device_id (string), e.g. "pi-001"
    Attributes: temp_min, temp_max, humidity_min, humidity_max, pressure_min, pressure_max

Do NOT use legacy ``id`` = ``global`` (causes ValidationException on current tables).
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal
from typing import Any, Dict, Mapping, Tuple

import boto3

logger = logging.getLogger(__name__)

SETTINGS_TABLE_NAME = os.environ.get("SETTINGS_TABLE_NAME", "DeviceSettings")
DEFAULT_DEVICE_ID = os.environ.get(
    "SETTINGS_DEVICE_ID",
    os.environ.get("DEVICE_ID", "pi-001"),
).strip() or "pi-001"

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

_FIELD_ALIASES: Dict[str, Tuple[str, ...]] = {
    "temp_min": ("temp_min", "temperature_min", "min_temp", "tempMin"),
    "temp_max": ("temp_max", "temperature_max", "max_temp", "tempMax"),
    "humidity_min": ("humidity_min", "hum_min", "min_humidity", "humidityMin"),
    "humidity_max": ("humidity_max", "hum_max", "max_humidity", "humidityMax"),
    "pressure_min": ("pressure_min", "pressure_low", "min_pressure", "pressureMin"),
    "pressure_max": ("pressure_max", "pressure_high", "max_pressure", "pressureMax"),
}

_dynamodb = boto3.resource("dynamodb")


def resolve_device_id(device_id: str | None = None) -> str:
    """Device partition key for DeviceSettings (aligns with SensorData.device_id)."""
    raw = (device_id or DEFAULT_DEVICE_ID or "pi-001").strip()
    return raw or "pi-001"


def canonical_partition_key(device_id: str | None = None) -> Dict[str, str]:
    """DynamoDB key: ``{"device_id": "pi-001"}``."""
    did = resolve_device_id(device_id)
    return {"device_id": did}


def decimal_to_native(obj: Any) -> Any:
    if isinstance(obj, list):
        return [decimal_to_native(v) for v in obj]
    if isinstance(obj, dict):
        return {k: decimal_to_native(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    return obj


def normalize_settings_dict(raw: Mapping[str, Any]) -> Dict[str, float]:
    """Map aliases to canonical threshold keys (excludes device_id)."""
    if not raw:
        return dict(DEFAULT_SETTINGS)

    out: Dict[str, float] = {}
    for canonical, aliases in _FIELD_ALIASES.items():
        value = None
        for alias in aliases:
            if alias in raw and raw[alias] is not None:
                value = raw[alias]
                break
        if value is not None:
            try:
                out[canonical] = float(value)
            except (TypeError, ValueError):
                pass

    if len(out) == len(_REQUIRED_FIELDS):
        return out

    merged = dict(DEFAULT_SETTINGS)
    merged.update(out)
    if out:
        logger.warning(
            "Settings row missing some canonical fields; merged with defaults. had=%s",
            list(out.keys()),
        )
    return merged


def _item_to_settings(item: Dict[str, Any]) -> Dict[str, float]:
    """Strip partition key and metadata; return threshold fields only."""
    skip = {
        "device_id",
        "id",
        "settings_id",
        "pk",
        "updated_at",
        "created_at",
    }
    payload = {k: v for k, v in item.items() if k not in skip}
    return normalize_settings_dict(payload)


def load_settings(
    table_name: str | None = None,
    device_id: str | None = None,
) -> Dict[str, float]:
    """
    Read threshold settings for one device from DeviceSettings.

    Key: ``{"device_id": "<device_id>"}`` (default pi-001).
    """
    name = table_name or SETTINGS_TABLE_NAME
    did = resolve_device_id(device_id)
    key = canonical_partition_key(did)

    logger.info(
        "[DEBUG] DynamoDB settings key=device_id:%s table=%s operation=get_item",
        did,
        name,
    )

    try:
        table = _dynamodb.Table(name)
        response = table.get_item(Key=key)
        item = response.get("Item")
        if item:
            settings = _item_to_settings(decimal_to_native(item))
            logger.info(
                "[DEBUG] DynamoDB settings loaded device_id:%s -> temp_max=%s",
                did,
                settings.get("temp_max"),
            )
            return settings
    except Exception as exc:
        logger.exception(
            "[DEBUG] DynamoDB get_item failed table=%s key=device_id:%s error=%s",
            name,
            did,
            exc,
        )

    logger.warning(
        "No settings row in %s for device_id:%s; returning DEFAULT_SETTINGS.",
        name,
        did,
    )
    return dict(DEFAULT_SETTINGS)


def validate_settings_payload(payload: Dict[str, Any]) -> Dict[str, Decimal]:
    """Validate POST body; accepts canonical names and aliases."""
    body = dict(payload or {})
    body.pop("device_id", None)

    normalized = normalize_settings_dict(body)
    missing = [k for k in _REQUIRED_FIELDS if k not in normalized]
    if missing:
        raise ValueError(f"Missing required field(s): {', '.join(missing)}")

    try:
        values: Dict[str, Decimal] = {}
        for key in _REQUIRED_FIELDS:
            values[key] = Decimal(str(float(normalized[key])))
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


def save_settings(
    values: Dict[str, Decimal],
    table_name: str | None = None,
    device_id: str | None = None,
) -> Dict[str, float]:
    """
    Persist settings for one device and re-read from DynamoDB.

    Item shape: ``{"device_id": "pi-001", "temp_min": ..., ...}``.
    """
    name = table_name or SETTINGS_TABLE_NAME
    did = resolve_device_id(device_id)
    key = canonical_partition_key(did)

    logger.info(
        "[DEBUG] DynamoDB settings key=device_id:%s table=%s operation=put_item",
        did,
        name,
    )

    table = _dynamodb.Table(name)
    item = {**key, **values}
    table.put_item(Item=item)

    written = {k: float(v) for k, v in values.items()}
    loaded = load_settings(name, device_id=did)

    if loaded == DEFAULT_SETTINGS and written != DEFAULT_SETTINGS:
        logger.error(
            "Settings put_item succeeded but get_item returned defaults. "
            "table=%s key=device_id:%s — verify DeviceSettings partition key is device_id.",
            name,
            did,
        )
        return written

    logger.info(
        "[DEBUG] DynamoDB settings saved device_id:%s temp_max=%s",
        did,
        loaded.get("temp_max"),
    )
    return loaded


def settings_for_response(values: Dict[str, Decimal] | Dict[str, float]) -> Dict[str, float]:
    """JSON-serializable floats for API responses."""
    return {k: float(v) for k, v in values.items()}
