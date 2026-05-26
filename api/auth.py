"""Session management — login/register via AWS auth_handler Lambda."""

from __future__ import annotations

import logging
from typing import Dict, Optional

from flask import session
from werkzeug.security import check_password_hash, generate_password_hash

from cloud.client import CloudAPIClient, CloudClientError
from config import Config, get_config

logger = logging.getLogger("smart_env_monitor.auth")


def get_admin_username() -> str:
    return str(getattr(Config, "ADMIN_USERNAME", "admin")).strip()


def get_admin_password() -> str:
    return str(getattr(Config, "ADMIN_PASSWORD", ""))


def get_admin_password_hash() -> str:
    return str(getattr(Config, "ADMIN_PASSWORD_HASH", "")).strip()


def get_auth_config_summary() -> Dict[str, object]:
    return {
        "admin_username": get_admin_username(),
        "password_hash_configured": bool(get_admin_password_hash()),
        "use_aws_brain": getattr(Config, "USE_AWS_BRAIN", True),
        "local_auth_fallback": not getattr(Config, "USE_AWS_BRAIN", True),
    }


def _cloud_client() -> CloudAPIClient:
    return CloudAPIClient(get_config())


def login_user(username: str, *, token: Optional[str] = None) -> None:
    session["logged_in"] = True
    session["username"] = str(username).strip()
    session.permanent = True
    if token:
        session["aws_token"] = token
    logger.info("User '%s' logged in (session created after AWS auth).", username)


def logout_user() -> Optional[str]:
    username = session.get("username")
    session.clear()
    if username:
        logger.info("User '%s' logged out.", username)
    return username


def is_logged_in() -> bool:
    return bool(session.get("logged_in"))


def get_current_username(default: str = "") -> str:
    return str(session.get("username", default))


def verify_credentials_local(username: str, password: str) -> bool:
    """Deprecated — kept for backwards compatibility only."""
    username = str(username or "").strip()
    password = str(password or "")
    if username != get_admin_username():
        return False

    password_hash = get_admin_password_hash()
    if password_hash:
        try:
            return check_password_hash(password_hash, password)
        except Exception as exc:
            logger.exception("Password hash verification failed: %s", exc)
            return False

    fallback_password = get_admin_password()
    if not fallback_password:
        return False
    return password == fallback_password


def build_login_result(username: str, password: str) -> Dict[str, object]:
    username = str(username or "").strip()
    password = str(password or "")

    try:
        result = _cloud_client().post_login({"username": username, "password": password})
    except CloudClientError as exc:
        logger.warning("AWS login failed: %s", exc)
        return {
            "success": False,
            "source": "aws",
            "message": str(exc),
            "error_code": exc.error_code or "AWS_API_UNAVAILABLE",
            "fallback_used": False,
        }

    if result.get("success"):
        login_user(str(result.get("username") or username), token=result.get("token"))
        return {
            "success": True,
            "source": "aws",
            "message": result.get("message", "Login successful."),
            "username": get_current_username(),
        }

    return {
        "success": False,
        "source": "aws",
        "message": result.get("message", "Invalid username or password."),
        "error_code": result.get("error_code"),
        "fallback_used": False,
    }


def build_register_result(username: str, email: str, password: str) -> Dict[str, object]:
    username = str(username or "").strip()
    email = str(email or "").strip()
    password = str(password or "")

    if not username or not email or not password:
        return {
            "success": False,
            "source": "aws",
            "message": "Username, email and password are required.",
            "error_code": "validation_error",
        }

    try:
        result = _cloud_client().post_register(
            {"username": username, "email": email, "password": password}
        )
    except CloudClientError as exc:
        return {
            "success": False,
            "source": "aws",
            "message": str(exc),
            "error_code": exc.error_code or "AWS_API_UNAVAILABLE",
            "fallback_used": False,
        }

    if result.get("success"):
        return {
            "success": True,
            "source": "aws",
            "message": result.get("message", "Registration successful."),
            "username": result.get("username", username),
        }

    return {
        "success": False,
        "source": "aws",
        "message": result.get("message", "Registration failed."),
        "error_code": result.get("error_code"),
    }


def verify_credentials(username: str, password: str) -> bool:
    return bool(build_login_result(username, password).get("success"))


def generate_password_hash_for_env(password: str) -> str:
    return generate_password_hash(str(password))
