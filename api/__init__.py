"""Flask application factory (Assignment 2)."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from cloud.client import CloudAPIClient
from config import PROJECT_ROOT, get_config
from sensor import runtime as rt
from sensor.collector import collect_reading_and_upload
from utils.logging_utils import setup_logging

logger = logging.getLogger("smart_env_monitor.api")


_worker_started = False
_worker_lock = threading.Lock()


def create_app() -> Flask:
    Config = get_config()
    setup_logging(Config.LOG_LEVEL)

    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
    )
    app.config.from_object(Config)
    app.config["CONFIG_CLASS"] = Config
    app.secret_key = app.config.get("SECRET_KEY", "change-this-secret-key")
    app.extensions["cloud_client"] = CloudAPIClient(Config)

    from api.pages import pages_bp
    from api.routes import api_bp

    app.register_blueprint(api_bp)
    app.register_blueprint(pages_bp)

    if getattr(Config, "USE_SQLITE_CACHE", False):
        try:
            from legacy.database import init_db

            init_db()
        except Exception as exc:
            logger.warning("SQLite cache init: %s", exc)

    try:
        from legacy.display_service import show_startup_message

        show_startup_message()
    except Exception:
        pass

    if getattr(Config, "ENABLE_BACKGROUND_COLLECTOR", False):
        start_background_worker(app)
    else:
        logger.info(
            "Background sensor collector disabled; dashboard will read cloud data only."
        )
        rt.runtime_state["collector_thread_alive"] = False

    @app.get("/health")
    def root_health():
        return jsonify({"status": "ok", "service": "smart-env-monitor", "assignment": "2"}), 200

    @app.errorhandler(Exception)
    def _handle_unexpected(exc):
        if isinstance(exc, HTTPException):
            return exc
        logger.warning("Unhandled exception: %s", exc)
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "message": "Internal server error.", "error": str(exc)}), 500
        return ("Internal server error.", 500)

    return app


def start_background_worker(app: Flask) -> Optional[threading.Thread]:
    global _worker_started
    if app.config.get("DEBUG") and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return None
    with _worker_lock:
        if _worker_started:
            return None
        cfg = app.config["CONFIG_CLASS"]
        interval = int(app.config.get("SENSOR_INTERVAL", getattr(cfg, "SENSOR_INTERVAL", 5)))

        def _worker():
            logger.info("Sensor upload worker started (interval=%ss).", interval)
            rt.runtime_state["collector_thread_alive"] = True
            last_log = 0.0
            last_err: Optional[str] = None
            throttle = int(getattr(cfg, "LOG_THROTTLE_SECONDS", 60))
            while True:
                rt.runtime_state["last_collection_attempt_at"] = rt.safe_iso_now()
                try:
                    ok = collect_reading_and_upload(cfg)
                except Exception as exc:
                    ok = False
                    rt.runtime_state["last_error"] = str(exc)
                    now = time.monotonic()
                    if app.config.get("DEBUG") or str(exc) != last_err or (now - last_log) > throttle:
                        logger.warning("Collector error: %s", exc)
                        last_log = now
                        last_err = str(exc)
                    try:
                        from legacy.display_service import show_system_error

                        show_system_error("UPLOAD ERR")
                    except Exception:
                        pass
                if ok:
                    rt.runtime_state["last_collection_success_at"] = rt.safe_iso_now()
                    rt.runtime_state["consecutive_collection_failures"] = 0
                    rt.runtime_state["total_collection_successes"] = int(
                        rt.runtime_state.get("total_collection_successes", 0)
                    ) + 1
                else:
                    rt.runtime_state["consecutive_collection_failures"] = int(
                        rt.runtime_state.get("consecutive_collection_failures", 0)
                    ) + 1
                    rt.runtime_state["total_collection_failures"] = int(
                        rt.runtime_state.get("total_collection_failures", 0)
                    ) + 1
                time.sleep(max(1, interval))

        t = threading.Thread(target=_worker, daemon=True, name="CloudSensorUploader")
        t.start()
        _worker_started = True
        return t
