"""HTML routes: login, logout, dashboard shell (Flask templates)."""

from __future__ import annotations

from functools import wraps

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from api.auth import build_login_result, get_current_username, is_logged_in, logout_user
from config import get_config

pages_bp = Blueprint("pages", __name__)


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        cfg = current_app.config.get("CONFIG_CLASS", get_config())
        if getattr(cfg, "DISABLE_AUTH", False):
            return view_func(*args, **kwargs)
        if not is_logged_in():
            return redirect(url_for("pages.login"))
        return view_func(*args, **kwargs)

    return wrapper


@pages_bp.route("/login", methods=["GET", "POST"])
def login():
    cfg = current_app.config.get("CONFIG_CLASS", get_config())
    if getattr(cfg, "DISABLE_AUTH", False):
        return redirect(url_for("pages.dashboard"))

    if request.method == "GET":
        if is_logged_in():
            return redirect(url_for("pages.dashboard"))
        return render_template("login.html")

    data = request.form or request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", "")).strip()
    result = build_login_result(username, password)
    if result["success"]:
        return redirect(url_for("pages.dashboard"))
    return render_template("login.html", error=result["message"]), 401


@pages_bp.route("/logout", methods=["GET", "POST"])
def logout():
    try:
        logout_user()
    except Exception:
        session.clear()
    try:
        flash("You have been logged out.")
    except Exception:
        pass
    return redirect(url_for("pages.login"))


@pages_bp.route("/")
def home():
    cfg = current_app.config.get("CONFIG_CLASS", get_config())
    if getattr(cfg, "DISABLE_AUTH", False) or is_logged_in():
        return redirect(url_for("pages.dashboard"))
    return redirect(url_for("pages.login"))


@pages_bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("index.html", username=get_current_username())
