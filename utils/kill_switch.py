import json
import os
import tempfile
from typing import Any, Dict, Optional

from utils.heartbeat import utc_now_z


class KillSwitchStore:
    def __init__(self, lock_path: Optional[str] = None, state_path: Optional[str] = None):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        runtime_dir = os.getenv("RUNTIME_STATE_DIR", os.path.join(project_root, "runtime"))
        self.lock_path = lock_path or os.path.join(project_root, "kill_switch.lock")
        self.state_path = state_path or os.getenv(
            "KILL_SWITCH_STATE_PATH",
            os.path.join(runtime_dir, "kill_switch.json"),
        )
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)

    def _default_doc(self) -> Dict[str, Any]:
        return {
            "locked": False,
            "lock_file_present": False,
            "updated_at": utc_now_z(),
            "triggered_at": None,
            "cleared_at": None,
            "reason": None,
            "source": None,
            "recovery_hint": "排查原因后删除 kill_switch.lock 或清空结构化状态再恢复运行。",
            "trigger_event": None,
            "history": [],
        }

    def load(self) -> Dict[str, Any]:
        doc = self._default_doc()
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    doc.update(data)
            except Exception:
                pass

        lock_present = os.path.exists(self.lock_path)
        doc["lock_file_present"] = lock_present
        if lock_present:
            doc["locked"] = True
            if not doc.get("triggered_at"):
                doc["triggered_at"] = utc_now_z()
            if not doc.get("reason"):
                doc["reason"] = self._read_legacy_reason()
            if not doc.get("source"):
                doc["source"] = "legacy_lock_file"
        doc["updated_at"] = utc_now_z()
        return doc

    def save(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(doc or {})
        payload["updated_at"] = utc_now_z()
        parent = os.path.dirname(self.state_path) or "."
        os.makedirs(parent, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix="kill_switch_", suffix=".json", dir=parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.state_path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        return payload

    def _read_legacy_reason(self) -> Optional[str]:
        if not os.path.exists(self.lock_path):
            return None
        try:
            with open(self.lock_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read().strip()
            return text or None
        except Exception:
            return None

    def is_locked(self) -> bool:
        return bool(self.load().get("locked"))

    def trigger(
        self,
        *,
        reason: str,
        source: str,
        trigger_event: Optional[Dict[str, Any]] = None,
        recovery_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        doc = self.load()
        now = utc_now_z()
        event = {
            "ts": now,
            "action": "triggered",
            "reason": str(reason or "").strip() or "unknown",
            "source": str(source or "unknown"),
        }
        if isinstance(trigger_event, dict) and trigger_event:
            event["meta"] = trigger_event

        history = doc.get("history")
        if not isinstance(history, list):
            history = []
        history.insert(0, event)

        doc.update(
            {
                "locked": True,
                "lock_file_present": True,
                "triggered_at": doc.get("triggered_at") or now,
                "reason": event["reason"],
                "source": event["source"],
                "recovery_hint": recovery_hint
                or doc.get("recovery_hint")
                or "排查原因后删除 kill_switch.lock 或清空结构化状态再恢复运行。",
                "trigger_event": trigger_event if isinstance(trigger_event, dict) else None,
                "history": history[:20],
                "cleared_at": None,
            }
        )

        with open(self.lock_path, "w", encoding="utf-8") as f:
            f.write(f"Kill Switch Triggered Reason: {event['reason']}\n")
            f.write(f"Source: {event['source']}\n")
            f.write(f"Triggered At: {now}\n")
        return self.save(doc)

    def clear(self, *, reason: str = "manual_clear") -> Dict[str, Any]:
        doc = self.load()
        now = utc_now_z()
        history = doc.get("history")
        if not isinstance(history, list):
            history = []
        history.insert(
            0,
            {
                "ts": now,
                "action": "cleared",
                "reason": str(reason or "manual_clear"),
                "source": "manual",
            },
        )
        doc.update(
            {
                "locked": False,
                "lock_file_present": False,
                "cleared_at": now,
                "history": history[:20],
            }
        )
        if os.path.exists(self.lock_path):
            os.remove(self.lock_path)
        return self.save(doc)
