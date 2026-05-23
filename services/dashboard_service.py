"""Dashboard payload router: AWS proxy when enabled, else local_fallback."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from cloud.client import CloudAPIClient, CloudClientError
from config import get_config
from services.aws_proxy import aws_unavailable_error, build_aws_dashboard_response
from services.local_fallback import build_local_fallback_payload

logger = logging.getLogger("smart_env_monitor.services.dashboard")


def build_dashboard_payload(
    app,
    cloud_client: CloudAPIClient,
    device_id: Optional[str] = None,
) -> Dict[str, Any]:
    cfg_class = app.config.get("CONFIG_CLASS", get_config())
    use_aws = bool(getattr(cfg_class, "USE_AWS_BRAIN", True))

    if use_aws:
        try:
            return build_aws_dashboard_response(app, cloud_client, device_id=device_id)
        except CloudClientError as exc:
            logger.warning("AWS Brain /data failed: %s", exc)
            from sensor import runtime as rt

            rt.mark_cloud_fetch(False, str(exc))
            if getattr(cfg_class, "LOCAL_FALLBACK_ON_AWS_ERROR", False):
                return build_local_fallback_payload(app, error_message=str(exc))
            err = aws_unavailable_error(exc)
            err.update(
                {
                    "latest": None,
                    "settings": None,
                    "warnings": [],
                    "warning_status": {
                        "has_warning": False,
                        "count": 0,
                        "messages": [],
                        "level": "error",
                    },
                    "warning_banner": str(exc),
                    "analysis": {
                        "spike_drop": "Unavailable — AWS API unreachable.",
                        "trend": "Unavailable — AWS API unreachable.",
                        "prediction": "Unavailable — AWS API unreachable.",
                    },
                    "chart_labels": [],
                    "chart_values": [],
                }
            )
            return err

    return build_local_fallback_payload(
        app,
        error_message="USE_AWS_BRAIN is disabled; using local fallback.",
    )
