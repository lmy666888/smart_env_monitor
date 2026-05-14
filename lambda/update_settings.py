"""
Backward-compatible entry point for deployments that still reference
``update_settings.lambda_handler``.

Prefer configuring API Gateway to use ``settings_handler.lambda_handler`` for
GET + POST + OPTIONS support.
"""

from settings_handler import lambda_handler

__all__ = ["lambda_handler"]
