"""
Sensor collection: read hardware/emulator, upload to AWS, optional SQLite cache.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from cloud.client import CloudAPIClient
from config import get_config
from sensor import runtime as rt
from sensor.reader import get_sensor_source_name, read_from_emulator

logger = logging.getLogger("smart_env_monitor.sensor.collector")


def _iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _maybe_update_sense_hat_led(reading: Dict[str, Any], cfg: type) -> None:
    """Update optional Sense HAT LED matrix using cached cloud thresholds."""
    try:
        from legacy.display_service import update_warning_display
    except Exception:
        return
    settings = rt.runtime_state.get("settings_cache") or getattr(
        cfg, "CLOUD_DEFAULT_SETTINGS", {}
    )
    if not settings:
        return
    latest = {
        "temperature": reading["temperature"],
        "humidity": reading["humidity"],
        "pressure": reading["pressure"],
        "timestamp": _iso_timestamp(),
    }
    try:
        if update_warning_display(latest, settings):
            rt.runtime_state["last_display_update_at"] = rt.safe_iso_now()
    except Exception:
        pass


def collect_reading_and_upload(config_class: Optional[type] = None) -> bool:
    """
    Read sensors, POST JSON to API Gateway ingest, optionally mirror to SQLite.

    Returns True if cloud upload succeeded. Never raises.
    """
    cfg = config_class or get_config()
    client = CloudAPIClient(cfg)

    reading = read_from_emulator()
    if not reading:
        rt.mark_cloud_upload(False, "no_reading")
        return False

    payload: Dict[str, Any] = {
        "device_id": getattr(cfg, "DEVICE_ID", "pi-001"),
        "temperature": reading["temperature"],
        "humidity": reading["humidity"],
        "pressure": reading["pressure"],
    }

    ok = client.post_sensor_reading(payload)
    if ok:
        rt.mark_cloud_upload(True)
        logger.info(
            "Cloud upload [src=%s] T=%.2f°C H=%.2f%% P=%.2f hPa",
            get_sensor_source_name(),
            reading["temperature"],
            reading["humidity"],
            reading["pressure"],
        )
        _maybe_update_sense_hat_led(reading, cfg)
    else:
        rt.mark_cloud_upload(False, "ingest_failed")

    if getattr(cfg, "USE_SQLITE_CACHE", False):
        _sqlite_cache_fallback(cfg, reading)

    return ok


def _sqlite_cache_fallback(cfg: type, reading: Dict[str, Any]) -> None:
    try:
        from legacy.database import insert_sensor_data

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        insert_sensor_data(
            reading["temperature"],
            reading["humidity"],
            reading["pressure"],
            timestamp=ts,
        )
    except Exception as exc:
        logger.debug("SQLite cache insert skipped: %s", exc)


def collect_and_store_reading(use_simulation_fallback: bool = False) -> bool:
    """Assignment 1 name preserved — now uploads to cloud instead of DB-only."""
    return collect_reading_and_upload()


def start_background_collection(
    interval_seconds: int = 5,
    use_simulation_fallback: bool = False,
    max_iterations: Optional[int] = None,
) -> None:
    safe_interval = max(1, int(interval_seconds))
    logger.info(
        "Background upload loop: source=%s interval=%ss",
        get_sensor_source_name(),
        safe_interval,
    )
    iteration = 0
    while True:
        try:
            collect_reading_and_upload()
        except Exception as exc:
            logger.warning("Collection loop error: %s", exc)
        iteration += 1
        if max_iterations is not None and iteration >= max_iterations:
            return
        time.sleep(safe_interval)
