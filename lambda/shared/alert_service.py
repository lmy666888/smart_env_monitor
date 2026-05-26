"""SNS email alerts with cooldown for threshold warnings."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3

logger = logging.getLogger(__name__)

SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "").strip()
ALERT_COOLDOWN_SECONDS = int(os.environ.get("ALERT_COOLDOWN_SECONDS", "600"))
ALERT_STATE_TABLE_NAME = os.environ.get("ALERT_STATE_TABLE_NAME", "").strip()

_sns_client: Any = None
_dynamodb = boto3.resource("dynamodb")
_memory_cooldown: Dict[str, str] = {}


def _sns() -> Any:
    global _sns_client
    if _sns_client is None:
        _sns_client = boto3.client("sns")
    return _sns_client


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _in_cooldown(alert_key: str) -> bool:
    if ALERT_STATE_TABLE_NAME:
        try:
            table = _dynamodb.Table(ALERT_STATE_TABLE_NAME)
            row = table.get_item(Key={"alert_key": alert_key}).get("Item")
            if row and row.get("last_sent_at"):
                last = _parse_iso(str(row["last_sent_at"]))
                if last:
                    age = (datetime.now(timezone.utc) - last).total_seconds()
                    if age < ALERT_COOLDOWN_SECONDS:
                        logger.info("SNS cooldown active for %s (%.0fs left)", alert_key, ALERT_COOLDOWN_SECONDS - age)
                        return True
        except Exception as exc:
            logger.warning("AlertState read failed, using memory cooldown: %s", exc)

    last_mem = _memory_cooldown.get(alert_key)
    if last_mem:
        last = _parse_iso(last_mem)
        if last:
            age = (datetime.now(timezone.utc) - last).total_seconds()
            if age < ALERT_COOLDOWN_SECONDS:
                return True
    return False


def _mark_sent(alert_key: str) -> None:
    now = _utc_now_iso()
    _memory_cooldown[alert_key] = now
    if not ALERT_STATE_TABLE_NAME:
        return
    try:
        table = _dynamodb.Table(ALERT_STATE_TABLE_NAME)
        table.put_item(Item={"alert_key": alert_key, "last_sent_at": now})
    except Exception as exc:
        logger.warning("AlertState write failed: %s", exc)


def _build_email_body(
    device_id: str,
    latest: Dict[str, Any],
    warnings: List[str],
    warning_status: Dict[str, Any],
) -> str:
    ts = latest.get("timestamp", "—")
    lines = [
        "Smart Environment Monitor — threshold alert",
        "",
        f"Device: {device_id}",
        f"Timestamp: {ts}",
        f"Level: {warning_status.get('level', 'warning')}",
        "",
        f"Temperature: {latest.get('temperature', '—')} °C",
        f"Humidity: {latest.get('humidity', '—')} %",
        f"Pressure: {latest.get('pressure', '—')} hPa",
        "",
        "Warnings:",
    ]
    for w in warnings:
        lines.append(f"  - {w}")
    return "\n".join(lines)


def maybe_send_warning_alert(
    *,
    device_id: str,
    latest: Optional[Dict[str, Any]],
    warnings: List[str],
    warning_status: Dict[str, Any],
) -> None:
    if not SNS_TOPIC_ARN:
        return
    if not latest or not warnings:
        return

    level = str(warning_status.get("level") or "").lower()
    if level not in ("warning", "critical"):
        return

    alert_key = f"{device_id}:{level}"
    if _in_cooldown(alert_key):
        return

    subject = f"[{level.upper()}] Env alert — {device_id}"
    body = _build_email_body(device_id, latest, warnings, warning_status)

    try:
        _sns().publish(TopicArn=SNS_TOPIC_ARN, Subject=subject[:100], Message=body)
        _mark_sent(alert_key)
        logger.info("SNS alert sent for %s level=%s", device_id, level)
    except Exception as exc:
        logger.warning("SNS publish failed (dashboard unaffected): %s", exc)
