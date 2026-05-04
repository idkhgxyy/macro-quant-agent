import json
import os
from datetime import datetime
from typing import Optional, Dict, Any

from utils.logger import setup_logger
logger = setup_logger(__name__)
from utils.file_rotate import append_with_rotation


def classify_exception(e: Exception) -> str:
    msg = str(e).lower()
    name = type(e).__name__.lower()

    if "rate limit" in msg or "too many requests" in msg or "ratelimit" in name:
        return "rate_limit"
    if "timeout" in msg or "timed out" in msg or "timeout" in name:
        return "timeout"
    if "unauthorized" in msg or "authentication" in msg or "forbidden" in msg:
        return "auth"
    if "quota" in msg or "insufficient" in msg or "exceeded" in msg:
        return "quota"
    if "connection refused" in msg or "connect" in msg and "failed" in msg:
        return "connect_failed"
    return "unknown"


def emit_event(component: str, level: str, event_type: str, message: str, meta: Optional[Dict[str, Any]] = None):
    payload = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "level": level,
        "component": component,
        "type": event_type,
        "message": message,
        "meta": meta or {},
    }

    max_bytes = int(os.getenv("LOG_MAX_BYTES", "5000000"))
    backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))

    os.makedirs("events", exist_ok=True)
    append_with_rotation(
        os.path.join("events", "events.jsonl"),
        json.dumps(payload, ensure_ascii=False) + "\n",
        max_bytes=max_bytes,
        backup_count=backup_count,
    )

    if level in {"ERROR", "CRITICAL"}:
        os.makedirs("alerts", exist_ok=True)
        append_with_rotation(
            os.path.join("alerts", "alerts.jsonl"),
            json.dumps(payload, ensure_ascii=False) + "\n",
            max_bytes=max_bytes,
            backup_count=backup_count,
        )

    if level == "CRITICAL":
        logger.error(f"🛑 [ALERT] {component} {event_type}: {message}")
    elif level == "ERROR":
        logger.error(f"❌ [EVENT] {component} {event_type}: {message}")
    else:
        logger.warning(f"⚠️ [EVENT] {component} {event_type}: {message}")
