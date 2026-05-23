"""
Centralised configuration (Assignment 2).

Loads `.env` and environment variables. Used by Flask, sensor collector,
cloud clients, and utilities.
"""

import os
import platform
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv

from config import cloud_config

# Project root: parent of the `config` package directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


def _to_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _resolve_db_path(name: str) -> str:
    p = Path(name)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def _default_api_base() -> str:
    return cloud_config.AWS_API_BASE_URL


class Config:
    """Base configuration."""

    FLASK_ENV = os.getenv("FLASK_ENV", "production").lower()
    SECRET_KEY = os.getenv("SECRET_KEY", "replace-this-secret-key")
    DEBUG = _to_bool(os.getenv("FLASK_DEBUG"), False)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8

    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "5001"))

    # SQLite: optional cache / local fallback only (not primary store).
    DB_NAME = os.getenv("DB_NAME", "sensor.db")
    DB_PATH = _resolve_db_path(DB_NAME)
    USE_SQLITE_CACHE = _to_bool(os.getenv("USE_SQLITE_CACHE"), False)

    # Legacy local-auth env vars (deprecated when USE_AWS_BRAIN=true).
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
    ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")
    # Only honoured when FLASK_ENV=development (see config.auth_utils.is_auth_disabled).
    DISABLE_AUTH = _to_bool(os.getenv("DISABLE_AUTH"), False)

    USE_AWS_BRAIN = True
    LOCAL_FALLBACK_ON_AWS_ERROR = False
    DEVICE_API_KEY = cloud_config.DEVICE_API_KEY
    SNS_TOPIC_ARN = cloud_config.SNS_TOPIC_ARN
    ENABLE_BACKGROUND_COLLECTOR = cloud_config.ENABLE_BACKGROUND_COLLECTOR
    DEMO_MODE = cloud_config.DEMO_MODE
    MOCK_UPLOAD_ENABLED = cloud_config.MOCK_UPLOAD_ENABLED
    AWS_REGION = cloud_config.AWS_REGION

    USE_SIMULATION = _to_bool(os.getenv("USE_SIMULATION"), False)
    USE_MOCK_SENSOR = _to_bool(os.getenv("USE_MOCK_SENSOR"), False)
    SENSOR_INTERVAL = int(os.getenv("SENSOR_INTERVAL", "5"))

    FALLBACK_TEMPERATURE = float(os.getenv("FALLBACK_TEMPERATURE", "22.0"))
    FALLBACK_HUMIDITY = float(os.getenv("FALLBACK_HUMIDITY", "50.0"))
    FALLBACK_PRESSURE = float(os.getenv("FALLBACK_PRESSURE", "1013.25"))

    SPIKE_THRESHOLD = float(os.getenv("SPIKE_THRESHOLD", "3.0"))
    TREND_WINDOW = int(os.getenv("TREND_WINDOW", "5"))
    STABILITY_THRESHOLD = float(os.getenv("STABILITY_THRESHOLD", "0.1"))

    ENABLE_SENSE_HAT = _to_bool(os.getenv("ENABLE_SENSE_HAT"), False)

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_THROTTLE_SECONDS = int(os.getenv("LOG_THROTTLE_SECONDS", "60"))

    # --- AWS HTTP API (API Gateway) — see config/cloud_config.py ---
    AWS_API_BASE = _default_api_base()
    AWS_INGEST_URL = os.getenv("AWS_INGEST_URL", cloud_config.endpoint_url(cloud_config.INGEST_ENDPOINT))
    AWS_DATA_URL = os.getenv("AWS_DATA_URL", cloud_config.endpoint_url(cloud_config.DATA_ENDPOINT))
    AWS_SETTINGS_URL = os.getenv(
        "AWS_SETTINGS_URL",
        cloud_config.endpoint_url(cloud_config.SETTINGS_ENDPOINT),
    )
    AWS_LOGIN_URL = os.getenv("AWS_LOGIN_URL", cloud_config.endpoint_url(cloud_config.LOGIN_ENDPOINT))
    AWS_REGISTER_URL = os.getenv(
        "AWS_REGISTER_URL",
        cloud_config.endpoint_url(cloud_config.REGISTER_ENDPOINT),
    )
    AWS_HEALTH_URL = os.getenv("AWS_HEALTH_URL", cloud_config.endpoint_url(cloud_config.HEALTH_ENDPOINT))
    CLOUD_TIMEOUT_SECONDS = cloud_config.CLOUD_TIMEOUT_SECONDS

    DEVICE_ID = os.getenv("DEVICE_ID", "pi-001")

    # Fallback thresholds (match Lambda defaults) when settings cache is empty.
    CLOUD_DEFAULT_SETTINGS: Dict[str, float] = {
        "temp_min": 0,
        "temp_max": 40,
        "humidity_min": 20,
        "humidity_max": 80,
        "pressure_min": 980,
        "pressure_max": 1030,
    }

    # HTTP client defaults (alias cloud timeout unless overridden)
    HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", str(cloud_config.CLOUD_TIMEOUT_SECONDS)))
    HTTP_MAX_RETRIES = int(os.getenv("HTTP_MAX_RETRIES", "3"))
    HTTP_RETRY_BACKOFF = float(os.getenv("HTTP_RETRY_BACKOFF", "0.6"))

    # Dashboard polling (browser → Flask `/api/data`, which calls AWS).
    DASHBOARD_CLOUD_TIMEOUT = cloud_config.DASHBOARD_CLOUD_TIMEOUT

    @classmethod
    def is_desktop_platform(cls) -> bool:
        return platform.system() in {"Darwin", "Windows"}

    @classmethod
    def to_dict(cls) -> dict:
        return {
            "FLASK_ENV": cls.FLASK_ENV,
            "DEBUG": cls.DEBUG,
            "HOST": cls.HOST,
            "PORT": cls.PORT,
            "DB_PATH": cls.DB_PATH,
            "USE_SQLITE_CACHE": cls.USE_SQLITE_CACHE,
            "ADMIN_USERNAME": cls.ADMIN_USERNAME,
            "ADMIN_PASSWORD_HASH_CONFIGURED": bool(cls.ADMIN_PASSWORD_HASH),
            "DISABLE_AUTH": cls.DISABLE_AUTH,
            "USE_SIMULATION": cls.USE_SIMULATION,
            "USE_MOCK_SENSOR": cls.USE_MOCK_SENSOR,
            "SENSOR_INTERVAL": cls.SENSOR_INTERVAL,
            "SPIKE_THRESHOLD": cls.SPIKE_THRESHOLD,
            "TREND_WINDOW": cls.TREND_WINDOW,
            "STABILITY_THRESHOLD": cls.STABILITY_THRESHOLD,
            "ENABLE_SENSE_HAT": cls.ENABLE_SENSE_HAT,
            "LOG_LEVEL": cls.LOG_LEVEL,
            "AWS_API_BASE": cls.AWS_API_BASE,
            "AWS_DATA_URL": cls.AWS_DATA_URL,
            "AWS_INGEST_URL": cls.AWS_INGEST_URL,
            "AWS_LOGIN_URL": cls.AWS_LOGIN_URL,
            "USE_AWS_BRAIN": cls.USE_AWS_BRAIN,
            "ENABLE_BACKGROUND_COLLECTOR": cls.ENABLE_BACKGROUND_COLLECTOR,
            "DEMO_MODE": cls.DEMO_MODE,
            "MOCK_UPLOAD_ENABLED": cls.MOCK_UPLOAD_ENABLED,
            "DEVICE_ID": cls.DEVICE_ID,
        }


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


def get_config():
    env = os.getenv("FLASK_ENV", "production").strip().lower()
    if env == "development":
        return DevelopmentConfig
    return ProductionConfig
