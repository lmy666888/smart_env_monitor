"""Dashboard payload — proxies to AWS."""

from __future__ import annotations

from typing import Any, Dict, Optional

from cloud.client import CloudAPIClient
from services.aws_proxy import build_aws_dashboard_response


def build_dashboard_payload(
    app,
    cloud_client: CloudAPIClient,
    device_id: Optional[str] = None,
) -> Dict[str, Any]:
    return build_aws_dashboard_response(app, cloud_client, device_id=device_id)
