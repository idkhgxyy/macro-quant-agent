import json
import os
import socket
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from config import AGENT_RUN_LOCK_STALE_SECONDS
from utils.heartbeat import HeartbeatStore, utc_now_z


def _parse_iso_ts(value: Optional[str]) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except Exception:
        return None


class RunLock:
    def __init__(self, path: Optional[str] = None, stale_after_seconds: Optional[int] = None):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        runtime_dir = os.getenv("RUNTIME_STATE_DIR", os.path.join(project_root, "runtime"))
        self.path: str = str(path or os.getenv("AGENT_RUN_LOCK_PATH", os.path.join(runtime_dir, "agent_run.lock")))
        self.stale_after_seconds = max(
            int(stale_after_seconds or AGENT_RUN_LOCK_STALE_SECONDS),
            60,
        )
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)

    def load(self) -> Optional[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            return None
        return None

    def _pid_exists(self, pid: object) -> bool:
        try:
            if not isinstance(pid, (int, str, bytes, bytearray)):
                return False
            value = int(pid)
        except Exception:
            return False
        if value <= 0:
            return False
        try:
            os.kill(value, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except Exception:
            return True
        return True

    def _stale_reason(self, payload: Optional[Dict[str, Any]]) -> Optional[str]:
        doc = payload if isinstance(payload, dict) else {}
        if not doc:
            return "invalid_lock_payload"

        lock_host = str(doc.get("host") or "")
        local_host = socket.gethostname()
        if lock_host and lock_host == local_host:
            pid = doc.get("pid")
            if pid is not None:
                if not self._pid_exists(pid):
                    return "owner_pid_not_alive"
                return None

        acquired_at = _parse_iso_ts(doc.get("acquired_at"))
        if acquired_at is not None:
            now = datetime.now(timezone.utc)
            age = (now - acquired_at.astimezone(timezone.utc)).total_seconds()
            if age >= float(self.stale_after_seconds):
                return "lock_expired"
        return None

    def _write_lock(self, payload: Dict[str, Any]) -> None:
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            try:
                os.remove(self.path)
            except OSError:
                pass
            raise

    def _clear_stale_lock(
        self,
        payload: Dict[str, Any],
        stale_reason: str,
        heartbeat_store: Optional[HeartbeatStore] = None,
    ) -> None:
        try:
            os.remove(self.path)
        except FileNotFoundError:
            return
        except OSError:
            return

        if heartbeat_store is not None:
            heartbeat_store.recover_stale_current(
                reason=f"stale_run_lock_recovered:{stale_reason}",
                pid=payload.get("pid"),
                host=payload.get("host"),
            )

    def acquire(
        self,
        *,
        owner_id: str,
        run_mode: str,
        date_str: str,
        heartbeat_store: Optional[HeartbeatStore] = None,
    ) -> Dict[str, Any]:
        payload = {
            "owner_id": str(owner_id or ""),
            "component": "daily_agent",
            "run_mode": str(run_mode or "manual"),
            "date": str(date_str or ""),
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "acquired_at": utc_now_z(),
        }

        for attempt in range(2):
            try:
                self._write_lock(payload)
                return {
                    "acquired": True,
                    "path": self.path,
                    "payload": payload,
                    "stale_recovered": attempt == 1,
                }
            except FileExistsError:
                existing = self.load() or {}
                stale_reason = self._stale_reason(existing)
                if stale_reason and attempt == 0:
                    self._clear_stale_lock(existing, stale_reason, heartbeat_store=heartbeat_store)
                    continue
                return {
                    "acquired": False,
                    "reason": "already_running",
                    "path": self.path,
                    "existing": existing,
                    "stale_reason": stale_reason,
                }

        return {
            "acquired": False,
            "reason": "already_running",
            "path": self.path,
            "existing": self.load() or {},
        }

    def release(self, owner_id: str) -> bool:
        payload = self.load()
        if not payload:
            return True
        if str(payload.get("owner_id") or "") != str(owner_id or ""):
            return False
        try:
            os.remove(self.path)
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return True
