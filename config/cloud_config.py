"""API Gateway URLs and feature flags (AWS is authoritative for brain logic)."""

from __future__ import annotations

import os
from typing import Dict

# Region documented for deployment; not used directly by HTTP client.
AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-2")

AWS_API_BASE_URL = os.getenv(
    "AWS_API_BASE_URL",
    os.getenv(
        "AWS_API_BASE",
        "https://9jzbd9a34j.execute-api.ap-southeast-2.amazonaws.com",
    ),
).rstrip("/")

DATA_ENDPOINT = os.getenv("DATA_ENDPOINT", "/data")
INGEST_ENDPOINT = os.getenv("INGEST_ENDPOINT", "/ingest")
SETTINGS_ENDPOINT = os.getenv("SETTINGS_ENDPOINT", "/settings")
LOGIN_ENDPOINT = os.getenv("LOGIN_ENDPOINT", "/login")
REGISTER_ENDPOINT = os.getenv("REGISTER_ENDPOINT", "/register")
HEALTH_ENDPOINT = os.getenv("HEALTH_ENDPOINT", "/health")

CLOUD_TIMEOUT_SECONDS = float(
    os.getenv("CLOUD_TIMEOUT_SECONDS", os.getenv("HTTP_TIMEOUT_SECONDS", "12"))
)
DASHBOARD_CLOUD_TIMEOUT = float(
    os.getenv("DASHBOARD_CLOUD_TIMEOUT", os.getenv("CLOUD_TIMEOUT_SECONDS", "15"))
)

USE_AWS_BRAIN = os.getenv("USE_AWS_BRAIN", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Optional: attempt SQLite/local analysis when AWS /data is unreachable.
LOCAL_FALLBACK_ON_AWS_ERROR = os.getenv("LOCAL_FALLBACK_ON_AWS_ERROR", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Flask background upload loop (sensor.collector). Default off for cloud demo mode.
ENABLE_BACKGROUND_COLLECTOR = os.getenv("ENABLE_BACKGROUND_COLLECTOR", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Explicit demo/mock cloud uploads (MacBook). When false, Flask reader must not
# silently substitute mock readings for failed emulator reads.
DEMO_MODE = os.getenv("DEMO_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}
MOCK_UPLOAD_ENABLED = os.getenv("MOCK_UPLOAD_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def endpoint_url(path: str) -> str:
    """Build full URL for an API Gateway path (leading slash required)."""
    base = AWS_API_BASE_URL.rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{base}{p}"


def all_endpoint_urls() -> Dict[str, str]:
    return {
        "data": endpoint_url(DATA_ENDPOINT),
        "ingest": endpoint_url(INGEST_ENDPOINT),
        "settings": endpoint_url(SETTINGS_ENDPOINT),
        "login": endpoint_url(LOGIN_ENDPOINT),
        "register": endpoint_url(REGISTER_ENDPOINT),
        "health": endpoint_url(HEALTH_ENDPOINT),
    }
