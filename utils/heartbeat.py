import json
import os
import socket
import tempfile
from datetime import datetime
from typing import Any, Dict, Optional


def utc_now_z() -> str:
    return datetime.utcnow().isoformat() + "Z"


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


def _duration_seconds(started_at: Optional[str], ended_at: Optional[str]) -> Optional[float]:
    start_dt = _parse_iso_ts(started_at)
    end_dt = _parse_iso_ts(ended_at)
    if not start_dt or not end_dt:
        return None
    try:
        return round(max((end_dt - start_dt).total_seconds(), 0.0), 6)
    except Exception:
        return None


class HeartbeatStore:
    def __init__(self, path: Optional[str] = None, recent_limit: Optional[int] = None):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        runtime_dir = os.getenv("RUNTIME_STATE_DIR", os.path.join(project_root, "runtime"))
        default_path = os.getenv("HEARTBEAT_STATE_PATH", os.path.join(runtime_dir, "heartbeat.json"))
        self.path = path or default_path
        self.recent_limit = max(int(recent_limit or os.getenv("HEARTBEAT_RECENT_RUNS", "20")), 1)
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    def _default_doc(self) -> Dict[str, Any]:
        return {
            "updated_at": utc_now_z(),
            "current": None,
            "last_run": None,
            "last_success": None,
            "recent_runs": [],
            "scheduler": {},
        }

    def load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return self._default_doc()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return self._default_doc()
            return {
                **self._default_doc(),
                **data,
            }
        except Exception:
            return self._default_doc()

    def save(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(doc or {})
        payload["updated_at"] = utc_now_z()
        parent = os.path.dirname(self.path) or "."
        os.makedirs(parent, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix="heartbeat_", suffix=".json", dir=parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        return payload

    def start_run(
        self,
        *,
        run_mode: str,
        date_str: str,
        broker: str,
        live_trading_enabled: bool,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        started_at = utc_now_z()
        run = {
            "run_id": f"{started_at}-{os.getpid()}",
            "component": "daily_agent",
            "status": "running",
            "run_mode": str(run_mode or "manual"),
            "date": str(date_str or ""),
            "broker": str(broker or ""),
            "live_trading_enabled": bool(live_trading_enabled),
            "started_at": started_at,
            "pid": os.getpid(),
            "host": socket.gethostname(),
        }
        if isinstance(extra, dict):
            run.update(extra)
        doc = self.load()
        doc["current"] = run
        self.save(doc)
        return run

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        error: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        doc = self.load()
        current = doc.get("current") if isinstance(doc.get("current"), dict) else {}
        base = dict(current) if str(current.get("run_id") or "") == str(run_id or "") else {"run_id": run_id}
        ended_at = utc_now_z()
        summary = {
            **base,
            "status": str(status or "unknown"),
            "ended_at": ended_at,
            "error": str(error or "").strip() or None,
        }
        if isinstance(extra, dict):
            summary.update(extra)
        duration_sec = _duration_seconds(summary.get("started_at"), ended_at)
        if duration_sec is not None:
            summary["duration_sec"] = duration_sec

        doc["current"] = None
        doc["last_run"] = summary
        if not summary.get("error"):
            doc["last_success"] = summary

        recent_runs = doc.get("recent_runs")
        if not isinstance(recent_runs, list):
            recent_runs = []
        recent_runs = [
            item
            for item in recent_runs
            if not (isinstance(item, dict) and str(item.get("run_id") or "") == str(run_id or ""))
        ]
        recent_runs.insert(0, summary)
        doc["recent_runs"] = recent_runs[: self.recent_limit]
        self.save(doc)
        return summary

    def recover_stale_current(
        self,
        *,
        reason: str,
        pid: Optional[int] = None,
        host: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        doc = self.load()
        current = doc.get("current")
        if not isinstance(current, dict) or not current:
            return None
        if pid is not None:
            try:
                current_pid = int(current.get("pid"))
            except Exception:
                current_pid = None
            if current_pid != int(pid):
                return None
        if host is not None and str(current.get("host") or "") != str(host):
            return None

        ended_at = utc_now_z()
        summary = {
            **current,
            "status": "stale_recovered",
            "ended_at": ended_at,
            "error": str(reason or "stale_current_recovered"),
            "stale_recovered": True,
        }
        duration_sec = _duration_seconds(summary.get("started_at"), ended_at)
        if duration_sec is not None:
            summary["duration_sec"] = duration_sec

        doc["current"] = None
        doc["last_run"] = summary

        recent_runs = doc.get("recent_runs")
        if not isinstance(recent_runs, list):
            recent_runs = []
        run_id = str(summary.get("run_id") or "")
        recent_runs = [
            item
            for item in recent_runs
            if not (isinstance(item, dict) and str(item.get("run_id") or "") == run_id)
        ]
        recent_runs.insert(0, summary)
        doc["recent_runs"] = recent_runs[: self.recent_limit]
        self.save(doc)
        return summary

    def update_scheduler(
        self,
        *,
        enabled: bool,
        loop_status: str,
        schedule_time: str,
        timezone: str,
        poll_seconds: int,
        next_run_at: Optional[str] = None,
        last_check_ts: Optional[str] = None,
        last_trigger_ts: Optional[str] = None,
        last_run_date: Optional[str] = None,
        message: Optional[str] = None,
    ) -> Dict[str, Any]:
        doc = self.load()
        scheduler = doc.get("scheduler") if isinstance(doc.get("scheduler"), dict) else {}
        scheduler.update(
            {
                "enabled": bool(enabled),
                "loop_status": str(loop_status or "unknown"),
                "schedule_time": str(schedule_time or ""),
                "timezone": str(timezone or ""),
                "poll_seconds": int(poll_seconds),
                "updated_at": utc_now_z(),
            }
        )
        if next_run_at is not None:
            scheduler["next_run_at"] = next_run_at
        if last_check_ts is not None:
            scheduler["last_check_ts"] = last_check_ts
        if last_trigger_ts is not None:
            scheduler["last_trigger_ts"] = last_trigger_ts
        if last_run_date is not None:
            scheduler["last_run_date"] = last_run_date
        if message is not None:
            scheduler["message"] = str(message)
        doc["scheduler"] = scheduler
        self.save(doc)
        return scheduler
