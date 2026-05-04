import json
import os
from datetime import datetime
from typing import Dict, Any


class ExecutionLedger:
    def __init__(self, dirpath: str = "ledger"):
        self.dirpath = dirpath
        os.makedirs(self.dirpath, exist_ok=True)

    def _path(self, date_str: str) -> str:
        safe_date = date_str.replace("/", "-")
        return os.path.join(self.dirpath, f"execution_{safe_date}.json")

    def save(self, date_str: str, payload: Dict[str, Any]):
        doc = {
            "kind": "execution",
            "date": date_str,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "payload": payload,
        }
        with open(self._path(date_str), "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)

