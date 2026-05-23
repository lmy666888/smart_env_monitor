"""Fill warnings/analysis from lambda/shared when /data payload is incomplete."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("smart_env_monitor.services.cloud_brain")

# Import lambda/shared/* as Lambda does (shared package lives under lambda/).
_LAMBDA_DIR = Path(__file__).resolve().parent.parent / "lambda"
if str(_LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(_LAMBDA_DIR))

from shared.analysis_service import analyze_temperature_trend  # noqa: E402
from shared.warnings_util import (  # noqa: E402
    generate_warnings,
    get_warning_status,
    warning_banner_text,
)

# Match lambda/shared/dynamo_settings.DEFAULT_SETTINGS (avoid importing boto3 on Flask).
DEFAULT_SETTINGS: Dict[str, float] = {
    "temp_min": 0,
    "temp_max": 40,
    "humidity_min": 20,
    "humidity_max": 80,
    "pressure_min": 980,
    "pressure_max": 1030,
}


def cloud_payload_has_brain_fields(payload: Dict[str, Any]) -> bool:
    """True if AWS already returned warnings + analysis objects."""
    if not isinstance(payload.get("warnings"), list):
        return False
    analysis = payload.get("analysis")
    if not isinstance(analysis, dict):
        return False
    return bool(analysis.keys() & {"spike_drop", "trend", "prediction"})


def settings_match_defaults(settings: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(settings, dict):
        return True
    try:
        for key, default_val in DEFAULT_SETTINGS.items():
            if float(settings.get(key, default_val)) != float(default_val):
                return False
        return True
    except (TypeError, ValueError):
        return False


def pick_settings_for_brain(
    cloud_settings: Optional[Dict[str, Any]],
    settings_cache: Optional[Dict[str, Any]],
) -> tuple[Dict[str, Any], str]:
    """
    Prefer saved thresholds from Flask cache when /data still has factory defaults.
    """
    if isinstance(settings_cache, dict) and settings_match_defaults(cloud_settings):
        if not settings_match_defaults(settings_cache):
            logger.warning(
                "[DEBUG] /api/data settings look like DEFAULTS; using settings_cache from last Save."
            )
            return dict(settings_cache), "settings_cache_merge"

    if isinstance(cloud_settings, dict) and cloud_settings:
        return dict(cloud_settings), "aws_lambda"

    if isinstance(settings_cache, dict) and settings_cache:
        return dict(settings_cache), "settings_cache_only"

    return dict(DEFAULT_SETTINGS), "defaults"


def compute_brain_fields(
    latest: Dict[str, Any],
    settings: Dict[str, Any],
    sensor_data: List[Dict[str, Any]],
    *,
    sensor_interval: int = 5,
) -> Dict[str, Any]:
    """Run lambda/shared warnings + analysis (same as get_dashboard_data Lambda)."""
    chron = list(reversed(sensor_data[-50:])) if sensor_data else []
    warnings = generate_warnings(latest, settings)
    warning_status = get_warning_status(latest, settings)
    warning_banner = warning_banner_text(latest, settings)
    analysis = analyze_temperature_trend(
        chron,
        settings,
        interval_seconds=sensor_interval,
    )
    return {
        "warnings": warnings,
        "warning_status": warning_status,
        "warning_banner": warning_banner,
        "analysis": analysis,
    }


def enrich_cloud_dashboard_payload(
    payload: Dict[str, Any],
    *,
    settings_cache: Optional[Dict[str, Any]] = None,
    sensor_interval: int = 5,
    force_recompute: bool = False,
) -> Dict[str, Any]:
    """
    Ensure warnings / warning_status / warning_banner / analysis exist on payload.

    Sets ``settings_source`` and ``analysis_source`` metadata for debugging.
    """
    latest = payload.get("latest")
    sensor_list = payload.get("sensor_data") or []
    if latest is None and sensor_list:
        latest = sensor_list[0]
        payload["latest"] = latest

    settings, settings_source = pick_settings_for_brain(
        payload.get("settings") if isinstance(payload.get("settings"), dict) else None,
        settings_cache,
    )
    payload["settings"] = settings
    payload["settings_source"] = settings_source

    if settings_source != "aws_lambda":
        force_recompute = True

    has_brain = cloud_payload_has_brain_fields(payload) and not force_recompute

    if has_brain and settings_source == "aws_lambda":
        payload["analysis_source"] = "aws_lambda"
        payload["warnings_source"] = "aws_lambda"
        return payload

    if not latest or not settings:
        payload.setdefault("warnings", payload.get("warnings") or [])
        payload.setdefault(
            "warning_status",
            payload.get("warning_status")
            or {"has_warning": False, "count": 0, "messages": [], "level": "normal"},
        )
        payload.setdefault(
            "warning_banner",
            payload.get("warning_banner") or "No data for threshold evaluation.",
        )
        payload.setdefault(
            "analysis",
            payload.get("analysis")
            or {
                "spike_drop": "No analysis available yet.",
                "trend": "No analysis available yet.",
                "prediction": "No analysis available yet.",
            },
        )
        payload["analysis_source"] = "none_missing_latest_or_settings"
        payload["warnings_source"] = payload.get("warnings_source", "none")
        return payload

    brain = compute_brain_fields(
        latest,
        settings,
        sensor_list if isinstance(sensor_list, list) else [],
        sensor_interval=sensor_interval,
    )
    payload.update(brain)

    if has_brain:
        payload["analysis_source"] = "aws_lambda"
        payload["warnings_source"] = "aws_lambda"
    else:
        reason = "lambda_shared_backfill"
        if settings_source != "aws_lambda":
            reason += f"+{settings_source}"
        payload["analysis_source"] = reason
        payload["warnings_source"] = reason
        logger.info(
            "[DEBUG] Brain fields computed via lambda/shared (%s). latest.temp=%s settings.temp_max=%s warnings=%s",
            reason,
            latest.get("temperature"),
            settings.get("temp_max"),
            brain.get("warnings"),
        )

    return payload
