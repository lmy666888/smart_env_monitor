"""Auth helpers."""


def is_auth_disabled(cfg_class: type) -> bool:
    """True only when FLASK_ENV=development AND DISABLE_AUTH=1."""
    env = str(getattr(cfg_class, "FLASK_ENV", "production")).strip().lower()
    disabled = bool(getattr(cfg_class, "DISABLE_AUTH", False))
    return env == "development" and disabled
