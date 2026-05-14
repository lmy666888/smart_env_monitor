"""Process-wide runtime state for the sensor upload worker and dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

runtime_state: Dict[str, Any] = {
    "app_started_at": datetime.now(timezone.utc).isoformat(),
    "collector_thread_alive": False,
    "last_collection_attempt_at": None,
    "last_collection_success_at": None,
    "last_cloud_upload_success_at": None,
    "last_cloud_upload_error": None,
    "last_cloud_fetch_success_at": None,
    "last_cloud_fetch_error": None,
    "cloud_api_reachable": None,
    "dynamodb_indicated_ok": None,
    "settings_cache": None,
    "last_display_update_at": None,
    "last_error": None,
    "consecutive_collection_failures": 0,
    "total_collection_successes": 0,
    "total_collection_failures": 0,
    "total_cloud_upload_successes": 0,
    "total_cloud_upload_failures": 0,
}


def safe_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def mark_cloud_fetch(ok: bool, error: Optional[str] = None) -> None:
    if ok:
        runtime_state["last_cloud_fetch_success_at"] = safe_iso_now()
        runtime_state["last_cloud_fetch_error"] = None
        runtime_state["cloud_api_reachable"] = True
    else:
        runtime_state["last_cloud_fetch_error"] = error
        runtime_state["cloud_api_reachable"] = False


def mark_cloud_upload(ok: bool, error: Optional[str] = None) -> None:
    if ok:
        runtime_state["last_cloud_upload_success_at"] = safe_iso_now()
        runtime_state["last_cloud_upload_error"] = None
        runtime_state["total_cloud_upload_successes"] = int(
            runtime_state.get("total_cloud_upload_successes", 0)
        ) + 1
        runtime_state["dynamodb_indicated_ok"] = True
    else:
        runtime_state["last_cloud_upload_error"] = error
        runtime_state["dynamodb_indicated_ok"] = False
        runtime_state["total_cloud_upload_failures"] = int(
            runtime_state.get("total_cloud_upload_failures", 0)
        ) + 1
