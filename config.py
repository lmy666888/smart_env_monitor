"""
config.py

Centralised configuration management for the smart environment monitoring system.

Loads environment variables from .env and provides structured configuration
for all modules (Flask, database, sensor, analysis, display).
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Base configuration shared across the application."""

    # =========================
    # Flask
    # =========================
    SECRET_KEY = os.getenv("SECRET_KEY", "default-secret-key")
    DEBUG = os.getenv("FLASK_DEBUG", "False") == "True"

    # =========================
    # Server
    # =========================
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 5000))

    # =========================
    # Database
    # =========================
    DB_NAME = os.getenv("DB_NAME", "sensor.db")

    # =========================
    # Sensor
    # =========================
    USE_SIMULATION = os.getenv("USE_SIMULATION", "True") == "True"
    SENSOR_INTERVAL = int(os.getenv("SENSOR_INTERVAL", 5))

    # =========================
    # Analysis
    # =========================
    SPIKE_THRESHOLD = float(os.getenv("SPIKE_THRESHOLD", 3.0))
    TREND_WINDOW = int(os.getenv("TREND_WINDOW", 5))

    # =========================
    # Sense HAT / Display
    # =========================
    ENABLE_SENSE_HAT = os.getenv("ENABLE_SENSE_HAT", "True") == "True"

    # =========================
    # Logging
    # =========================
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


class DevelopmentConfig(Config):
    """Development environment configuration."""
    DEBUG = True


class ProductionConfig(Config):
    """Production environment configuration."""
    DEBUG = False


def get_config():
    """
    Return appropriate configuration based on environment.

    You can switch using:
    export FLASK_ENV=development / production
    """
    env = os.getenv("FLASK_ENV", "production").lower()

    if env == "development":
        return DevelopmentConfig

    return ProductionConfig