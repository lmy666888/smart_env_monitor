"""
Lambda: GET and POST /settings

* **GET** — returns current threshold settings from DynamoDB (defaults if missing).
* **POST** — validates body and writes the singleton ``global`` row.

Supports **API Gateway HTTP API (v2)** and **REST API (v1)** event shapes.
Always returns JSON bodies (including 404/405) so clients never see a bare
``Not Found`` string without a structured envelope.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

from shared.dynamo_settings import (
    load_settings,
    save_settings,
    validate_settings_payload,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}


def _json_response(status_code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": dict(_CORS_HEADERS),
        "body": json.dumps(payload, default=str),
    }


def _parse_http_method(event: Dict[str, Any]) -> str:
    """HTTP API v2 vs REST API v1."""
    ctx = event.get("requestContext") or {}
    http = ctx.get("http")
    if isinstance(http, dict):
        m = http.get("method")
        if m:
            return str(m).upper()
    m = event.get("httpMethod")
    if m:
        return str(m).upper()
    return "GET"


def _parse_path(event: Dict[str, Any]) -> str:
    """Best-effort path for error messages."""
    req = event.get("requestContext", {}).get("http", {})
    if isinstance(req, dict) and req.get("path"):
        return str(req["path"])
    if event.get("path"):
        return str(event["path"])
    if event.get("rawPath"):
        return str(event["rawPath"])
    return "/settings"


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


def _handle_options() -> Dict[str, Any]:
    return {
        "statusCode": 204,
        "headers": dict(_CORS_HEADERS),
        "body": "",
    }


def _handle_get() -> Dict[str, Any]:
    settings = load_settings()
    return _json_response(
        200,
        {
            "success": True,
            "settings": settings,
        },
    )


def _handle_post(event: Dict[str, Any]) -> Dict[str, Any]:
    payload = _parse_body(event)
    try:
        values = validate_settings_payload(payload)
    except ValueError as exc:
        return _json_response(
            400,
            {
                "success": False,
                "error": "validation_error",
                "message": str(exc),
            },
        )
    try:
        save_settings(values)
    except Exception as exc:
        logger.exception("DynamoDB write failed: %s", exc)
        return _json_response(
            500,
            {
                "success": False,
                "error": "dynamodb_write_failed",
                "message": "Could not persist settings to DynamoDB.",
            },
        )
    return _json_response(
        200,
        {
            "success": True,
            "message": "Settings updated.",
            "settings": {k: float(v) for k, v in values.items()},
        },
    )


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    method = _parse_http_method(event)
    path = _parse_path(event)
    logger.info("settings_handler %s %s", method, path)

    if method == "OPTIONS":
        return _handle_options()

    if method == "GET":
        return _handle_get()

    if method == "POST":
        return _handle_post(event)

    return _json_response(
        405,
        {
            "success": False,
            "error": "method_not_allowed",
            "message": f"Method {method} is not supported. Use GET or POST.",
            "allowed_methods": ["GET", "POST", "OPTIONS"],
            "http_method": method,
            "path": path,
        },
    )


if __name__ == "__main__":
    from shared.dynamo_settings import DEFAULT_SETTINGS

    print(json.dumps(lambda_handler({"requestContext": {"http": {"method": "GET", "path": "/settings"}}}, None), indent=2))
    print(
        json.dumps(
            lambda_handler(
                {
                    "requestContext": {"http": {"method": "POST", "path": "/settings"}},
                    "body": json.dumps(DEFAULT_SETTINGS),
                },
                None,
            ),
            indent=2,
        )
    )
