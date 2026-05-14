import logging
from typing import Dict, Optional
from flask import session
from werkzeug.security import check_password_hash, generate_password_hash
from config import Config



logger = logging.getLogger("smart_env_monitor.auth")


# get admin username
def get_admin_username() -> str:
    """return admin username"""
    return str(getattr(Config, "ADMIN_USERNAME", "admin")).strip()

# get plain password (fallback)
def get_admin_password() -> str:
    """get fallback password"""
    return str(getattr(Config, "ADMIN_PASSWORD", "admin123"))



# get hashed password
def get_admin_password_hash() -> str:
    """get password hash"""
    return str(getattr(Config, "ADMIN_PASSWORD_HASH", "")).strip()

# simple config info (no secrets)
def get_auth_config_summary() -> Dict[str, object]:
    """return auth config info"""
    return {
        "admin_username": get_admin_username(),
        "password_hash_configured": bool(get_admin_password_hash()),
        "fallback_plain_password_enabled": bool(get_admin_password()),
    }

# check username + password
def verify_credentials(username: str, password: str) -> bool:
    """verify login"""
    username = str(username or "").strip()
    password = str(password or "")
    expected_username = get_admin_username()
    if username != expected_username:
        logger.warning("Authentication failed: username mismatch.")
        return False


    password_hash = get_admin_password_hash()
    # use hash if available
    if password_hash:
        try:
            success = check_password_hash(password_hash, password)
            if success:
                logger.info("Authentication succeeded using password hash.")
            else:
                logger.warning("Authentication failed: invalid password hash match.")
            return success
        except Exception as exc:
            logger.exception("Password hash verification failed: %s", exc)
            return False
    # fallback to plain password
    fallback_password = get_admin_password()
    success = password == fallback_password

    if success:
        logger.info("Authentication succeeded using fallback plain password.")
    else:
        logger.warning("Authentication failed: invalid plain password.")

    return success

# set login session
def login_user(username: str) -> None:
    """mark user logged in"""
    session["logged_in"] = True
    session["username"] = str(username).strip()
    session.permanent = True

    logger.info("User '%s' logged in and session created.", username)




# clear session
def logout_user() -> Optional[str]:
    """logout user"""
    username = session.get("username")
    session.clear()

    if username:
        logger.info("User '%s' logged out and session cleared.", username)
    else:
        logger.info("Anonymous session cleared.")

    return username

# check login state
def is_logged_in() -> bool:
    """check logged in"""
    return bool(session.get("logged_in"))
# get current user
def get_current_username(default: str = "admin") -> str:
    """get current username"""
    return str(session.get("username", default))
# login wrapper
def build_login_result(username: str, password: str) -> Dict[str, object]:
    """handle login result"""
    if verify_credentials(username, password):
        login_user(username)
        return {
            "success": True,
            "message": "Login successful.",
            "username": get_current_username(),
        }

    return {
        "success": False,
        "message": "Invalid username or password.",
    }



# generate password hash
def generate_password_hash_for_env(password: str) -> str:
    """generate hash for env"""
    return generate_password_hash(str(password))