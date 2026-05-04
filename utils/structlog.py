import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

from utils.logger import setup_logger
logger = setup_logger(__name__)
from utils.file_rotate import append_with_rotation


def log_struct(event: str, fields: Optional[Dict[str, Any]] = None, level: str = "INFO"):
    payload = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "event": event,
        "level": level,
        "fields": fields or {},
    }

    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    max_bytes = int(os.getenv("LOG_MAX_BYTES", "5000000"))
    backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    append_with_rotation(
        os.path.join(log_dir, "structured.jsonl"),
        json.dumps(payload, ensure_ascii=False) + "\n",
        max_bytes=max_bytes,
        backup_count=backup_count,
    )

    msg = json.dumps(payload, ensure_ascii=False)
    if level == "ERROR":
        logger.error(msg)
    elif level == "WARNING":
        logger.warning(msg)
    else:
        logger.info(msg)
