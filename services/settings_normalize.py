"""
Normalize threshold settings dicts from AWS / DynamoDB (canonical field names).

Mirrors ``lambda/shared/dynamo_settings.py`` alias rules for the Flask proxy layer.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

_ALIASES = {
    "temp_min": ("temp_min", "temperature_min", "min_temp"),
    "temp_max": ("temp_max", "temperature_max", "max_temp"),
    "humidity_min": ("humidity_min", "hum_min", "min_humidity"),
    "humidity_max": ("humidity_max", "hum_max", "max_humidity"),
    "pressure_min": ("pressure_min", "pressure_low", "min_pressure"),
    "pressure_max": ("pressure_max", "pressure_high", "max_pressure"),
}


def normalize_settings_dict(raw: Mapping[str, Any] | None) -> Dict[str, float] | None:
    if not raw:
        return None
    out: Dict[str, float] = {}
    for canonical, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in raw and raw[alias] is not None and raw[alias] != "":
                try:
                    out[canonical] = float(raw[alias])
                    break
                except (TypeError, ValueError):
                    continue
    if len(out) != len(_ALIASES):
        return None
    return out
