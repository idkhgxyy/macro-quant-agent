import json
import os
from datetime import datetime
from typing import Any, Dict

from utils.file_rotate import append_with_rotation


class MetricsDB:
    def __init__(self, dirpath: str = "metrics"):
        self.dirpath = dirpath
        os.makedirs(self.dirpath, exist_ok=True)

    def append(self, record: Dict[str, Any]):
        max_bytes = int(os.getenv("LOG_MAX_BYTES", "5000000"))
        backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))
        payload = {
            "ts": datetime.utcnow().isoformat() + "Z",
            **record,
        }
        append_with_rotation(
            os.path.join(self.dirpath, "metrics.jsonl"),
            json.dumps(payload, ensure_ascii=False) + "\n",
            max_bytes=max_bytes,
            backup_count=backup_count,
        )

