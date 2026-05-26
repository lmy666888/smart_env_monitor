"""Deprecated stub — brain logic lives in Lambda only."""

from __future__ import annotations

from typing import Any, Dict


def cloud_payload_has_brain_fields(payload: Dict[str, Any]) -> bool:
    if not isinstance(payload.get("warnings"), list):
        return False
    analysis = payload.get("analysis")
    if not isinstance(analysis, dict):
        return False
    return bool(analysis.keys() & {"spike_drop", "trend", "prediction"})


def enrich_cloud_dashboard_payload(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    raise RuntimeError(
        "Flask brain recompute is disabled. Deploy get_dashboard_data Lambda with shared/."
    )
