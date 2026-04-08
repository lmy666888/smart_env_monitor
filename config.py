import os
from dotenv import load_dotenv

# load .env values
load_dotenv()

# convert env string to bool
def _to_bool(value: str, default: bool = False) -> bool:
    """parse bool value"""
    if value is None:
        return default

    return str(value).strip().lower() in {"1", "true", "yes", "on"}

class Config:
    """base config"""

    # app config

    FLASK_ENV = os.getenv("FLASK_ENV", "production").lower()
    SECRET_KEY = os.getenv("SECRET_KEY", "replace-this-secret-key")
    DEBUG = _to_bool(os.getenv("FLASK_DEBUG"), False)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8

    # server config

    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 5000))


    # database

    DB_NAME = os.getenv("DB_NAME", "sensor.db")

    # login config
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
    ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")
    # sensor config
    USE_SIMULATION = _to_bool(os.getenv("USE_SIMULATION"), False)
    SENSOR_INTERVAL = int(os.getenv("SENSOR_INTERVAL", 5))

    # analysis config
    SPIKE_THRESHOLD = float(os.getenv("SPIKE_THRESHOLD", 3.0))
    TREND_WINDOW = int(os.getenv("TREND_WINDOW", 5))
    STABILITY_THRESHOLD = float(os.getenv("STABILITY_THRESHOLD", 0.1))


    # display
    ENABLE_SENSE_HAT = _to_bool(os.getenv("ENABLE_SENSE_HAT"), True)
    # logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()



    @classmethod
    def to_dict(cls) -> dict:
        """return safe config info"""
        return {
            "FLASK_ENV": cls.FLASK_ENV,
            "DEBUG": cls.DEBUG,
            "HOST": cls.HOST,
            "PORT": cls.PORT,
            "DB_NAME": cls.DB_NAME,
            "ADMIN_USERNAME": cls.ADMIN_USERNAME,
            "ADMIN_PASSWORD_HASH_CONFIGURED": bool(cls.ADMIN_PASSWORD_HASH),
            "USE_SIMULATION": cls.USE_SIMULATION,
            "SENSOR_INTERVAL": cls.SENSOR_INTERVAL,
            "SPIKE_THRESHOLD": cls.SPIKE_THRESHOLD,
            "TREND_WINDOW": cls.TREND_WINDOW,
            "STABILITY_THRESHOLD": cls.STABILITY_THRESHOLD,
            "ENABLE_SENSE_HAT": cls.ENABLE_SENSE_HAT,
            "LOG_LEVEL": cls.LOG_LEVEL,
        }




class DevelopmentConfig(Config):
    """dev config"""
    DEBUG = True

class ProductionConfig(Config):
    """prod config"""
    DEBUG = False
def get_config():
    """get config class"""
    env = os.getenv("FLASK_ENV", "production").strip().lower()

    if env == "development":
        return DevelopmentConfig

    return ProductionConfig