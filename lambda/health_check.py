"""Lambda GET /health — liveness probe."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(_event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    payload = {
        "status": "ok",
        "service": "smart-env-monitor",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
        },
        "body": json.dumps(payload),
    }


if __name__ == "__main__":
    print(json.dumps(lambda_handler({}, None), indent=2))
