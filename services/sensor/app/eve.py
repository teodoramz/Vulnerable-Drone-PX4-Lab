from __future__ import annotations

import json
import logging
from typing import Any

from app.models import Alert, Flow

logger = logging.getLogger("sensor.eve")


def parse_eve_line(line: str, default_iface: str = "") -> Alert | Flow | None:
    """Parse one eve.json line into an `Alert` or `Flow`.

    Returns None for other event types and for partial/malformed lines.
    """
    line = line.strip()
    if not line:
        return None

    try:
        event: dict[str, Any] = json.loads(line)
    except json.JSONDecodeError:
        logger.debug("skipping unparsable eve line: %r", line[:200])
        return None

    event_type = event.get("event_type")
    iface = event.get("in_iface") or default_iface

    if event_type == "alert":
        return _parse_alert(event, iface)
    if event_type == "flow":
        return _parse_flow(event, iface)
    return None


def _parse_alert(event: dict[str, Any], iface: str) -> Alert | None:
    alert = event.get("alert") or {}
    try:
        return Alert(
            ts=event["timestamp"],
            signature=alert["signature"],
            sid=alert["signature_id"],
            severity=alert.get("severity", 3),
            category=alert.get("category", ""),
            src_ip=event.get("src_ip", ""),
            src_port=event.get("src_port"),
            dest_ip=event.get("dest_ip", ""),
            dest_port=event.get("dest_port"),
            proto=event.get("proto", ""),
            iface=iface,
            payload=event.get("payload", "") or "",
            payload_printable=event.get("payload_printable", "") or "",
        )
    except KeyError as exc:
        logger.debug("alert event missing required field %s: %r", exc, event)
        return None


def _parse_flow(event: dict[str, Any], iface: str) -> Flow | None:
    flow = event.get("flow") or {}
    try:
        return Flow(
            ts=event["timestamp"],
            src_ip=event.get("src_ip", ""),
            src_port=event.get("src_port"),
            dest_ip=event.get("dest_ip", ""),
            dest_port=event.get("dest_port"),
            proto=event.get("proto", ""),
            iface=iface,
            state=flow.get("state", ""),
            pkts_toserver=flow.get("pkts_toserver", 0),
            pkts_toclient=flow.get("pkts_toclient", 0),
            bytes_toserver=flow.get("bytes_toserver", 0),
            bytes_toclient=flow.get("bytes_toclient", 0),
            start=flow.get("start", ""),
            end=flow.get("end", ""),
        )
    except KeyError as exc:
        logger.debug("flow event missing required field %s: %r", exc, event)
        return None
