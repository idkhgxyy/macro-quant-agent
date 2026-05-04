import json
import os
from datetime import datetime
from typing import Optional, Dict, Any


class SnapshotDB:
    def __init__(self, dirpath: str = "snapshots"):
        self.dirpath = dirpath
        os.makedirs(self.dirpath, exist_ok=True)

    def _path(self, kind: str, date_str: str) -> str:
        safe_date = date_str.replace("/", "-")
        return os.path.join(self.dirpath, f"{kind}_{safe_date}.json")

    def save_rag(self, date_str: str, payload: dict):
        doc = {
            "kind": "rag",
            "date": date_str,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "payload": payload,
        }
        with open(self._path("rag", date_str), "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)

    def load_rag(self, date_str: str) -> Optional[Dict[str, Any]]:
        p = self._path("rag", date_str)
        if not os.path.exists(p):
            return None
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_decision(self, date_str: str, payload: dict):
        doc = {
            "kind": "decision",
            "date": date_str,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "payload": payload,
        }
        with open(self._path("decision", date_str), "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)

    def load_decision(self, date_str: str) -> Optional[Dict[str, Any]]:
        p = self._path("decision", date_str)
        if not os.path.exists(p):
            return None
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
