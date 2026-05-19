"""
Lambda: POST /login and POST /register

Authenticates users against DynamoDB ``Users`` table (partition key: username).

Environment variables:
    USERS_TABLE_NAME   Default: Users
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict

import boto3
from werkzeug.security import check_password_hash, generate_password_hash

logger = logging.getLogger()
logger.setLevel(logging.INFO)

USERS_TABLE_NAME = os.environ.get("USERS_TABLE_NAME", "Users")
_dynamodb = boto3.resource("dynamodb")

_CORS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
}

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


def _json_response(status_code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": dict(_CORS),
        "body": json.dumps(payload, default=str),
    }


def _parse_method(event: Dict[str, Any]) -> str:
    ctx = event.get("requestContext") or {}
    http = ctx.get("http")
    if isinstance(http, dict) and http.get("method"):
        return str(http["method"]).upper()
    if event.get("httpMethod"):
        return str(event["httpMethod"]).upper()
    return "POST"


def _parse_body(event: Dict[str, Any]) -> Dict[str, Any]:
    body = (event or {}).get("body")
    if body is None:
        return {}
    if isinstance(body, dict):
        return body
    try:
        return json.loads(body)
    except (TypeError, ValueError):
        return {}


def _handle_register(payload: Dict[str, Any]) -> Dict[str, Any]:
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))

    if not _USERNAME_RE.match(username):
        return _json_response(
            400,
            {
                "success": False,
                "message": "Username must be 3–32 characters (letters, numbers, ._-).",
                "error_code": "validation_error",
            },
        )
    if len(password) < 6:
        return _json_response(
            400,
            {
                "success": False,
                "message": "Password must be at least 6 characters.",
                "error_code": "validation_error",
            },
        )

    table = _dynamodb.Table(USERS_TABLE_NAME)
    existing = table.get_item(Key={"username": username})
    if existing.get("Item"):
        return _json_response(
            409,
            {
                "success": False,
                "message": "Username already exists.",
                "error_code": "username_taken",
            },
        )

    table.put_item(
        Item={
            "username": username,
            "password_hash": generate_password_hash(password),
        }
    )
    return _json_response(
        201,
        {
            "success": True,
            "message": "Registration successful.",
            "username": username,
        },
    )


def _handle_login(payload: Dict[str, Any]) -> Dict[str, Any]:
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))

    if not username or not password:
        return _json_response(
            400,
            {
                "success": False,
                "message": "Username and password are required.",
                "error_code": "validation_error",
            },
        )

    table = _dynamodb.Table(USERS_TABLE_NAME)
    response = table.get_item(Key={"username": username})
    item = response.get("Item")
    if not item:
        return _json_response(
            401,
            {
                "success": False,
                "message": "Invalid username or password.",
                "error_code": "auth_failed",
            },
        )

    stored_hash = str(item.get("password_hash", ""))
    if not stored_hash or not check_password_hash(stored_hash, password):
        return _json_response(
            401,
            {
                "success": False,
                "message": "Invalid username or password.",
                "error_code": "auth_failed",
            },
        )

    return _json_response(
        200,
        {
            "success": True,
            "message": "Login successful.",
            "username": username,
        },
    )


def _resolve_path(event: Dict[str, Any]) -> str:
    req = (event.get("requestContext") or {}).get("http") or {}
    return str(
        req.get("path")
        or event.get("rawPath")
        or event.get("path")
        or ""
    ).lower()


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    method = _parse_method(event)
    if method == "OPTIONS":
        return {"statusCode": 204, "headers": dict(_CORS), "body": ""}

    payload = _parse_body(event)
    path = _resolve_path(event)

    if path.endswith("/register") or event.get("action") == "register":
        return _handle_register(payload)

    return _handle_login(payload)
