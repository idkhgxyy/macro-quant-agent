import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.events import emit_event
from utils.webhook import post_json


def _parse_ts(ts: str) -> Optional[float]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _load_jsonl(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _compact_alert(a: Dict[str, Any]) -> Dict[str, Any]:
    meta = a.get("meta")
    meta_str = None
    if meta is not None:
        try:
            meta_str = json.dumps(meta, ensure_ascii=False)
        except Exception:
            meta_str = str(meta)
        if isinstance(meta_str, str) and len(meta_str) > 300:
            meta_str = meta_str[:300]

    msg = a.get("message")
    if not isinstance(msg, str):
        msg = str(msg)
    if len(msg) > 200:
        msg = msg[:200]

    comp = a.get("component")
    if not isinstance(comp, str):
        comp = str(comp)
    typ = a.get("type")
    if not isinstance(typ, str):
        typ = str(typ)
    lvl = a.get("level")
    if not isinstance(lvl, str):
        lvl = str(lvl)
    ts = a.get("ts")
    if not isinstance(ts, str):
        ts = str(ts)

    out = {"ts": ts, "level": lvl, "component": comp, "type": typ, "message": msg}
    if meta_str:
        out["meta"] = meta_str
    return out


def _load_state(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(path: str, state: Dict[str, Any]):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def evaluate_and_notify(
    *,
    date_str: str,
    broker: str,
    status: str,
    run_start_ts: str,
    run_end_ts: str,
    webhook_url: Optional[str],
    cooldown_seconds: int,
    thresholds: Dict[str, int],
    auto_kill_switch: bool,
    include_recent_alerts: bool,
    recent_limit: int,
    state_path: str = os.path.join("alerts", "policy_state.json"),
    alerts_jsonl_path: str = os.path.join("alerts", "alerts.jsonl"),
):
    start_epoch = _parse_ts(run_start_ts) or 0.0
    end_epoch = _parse_ts(run_end_ts) or start_epoch
    if end_epoch < start_epoch:
        end_epoch = start_epoch

    alerts = _load_jsonl(alerts_jsonl_path)
    window = []
    for a in alerts[-800:]:
        ts = _parse_ts(str(a.get("ts", "")))
        if ts is None:
            continue
        if start_epoch <= ts <= end_epoch:
            window.append(a)

    data_failed = any(
        isinstance(x.get("component"), str)
        and x["component"].startswith("data.")
        and str(x.get("level", "")).upper() in {"ERROR", "CRITICAL"}
        for x in window
    )

    llm_invalid = status == "invalid"
    order_problem = status in {"cancelled", "rejected", "unfilled", "submitted_no_report"}
    exception = status == "exception"

    state = _load_state(state_path)
    counters = state.get("counters") if isinstance(state.get("counters"), dict) else {}

    def _bump(key: str, cond: bool):
        v = int(counters.get(key, 0) or 0)
        counters[key] = v + 1 if cond else 0

    _bump("data_failed", data_failed)
    _bump("llm_invalid", llm_invalid)
    _bump("order_problem", order_problem)
    _bump("exception", exception)

    state["counters"] = counters

    now_epoch = _parse_ts(datetime.utcnow().isoformat() + "Z") or 0.0
    last_notify_epoch = float(state.get("last_notify_epoch") or 0.0)
    last_notify_reason = str(state.get("last_notify_reason") or "")

    triggered = []
    for k, v in counters.items():
        th = int(thresholds.get(k, 0) or 0)
        if th > 0 and int(v) >= th:
            triggered.append((k, int(v), th))

    notify_triggered = False
    reason = None
    triggered_items = [{"key": k, "count": v, "threshold": th} for k, v, th in triggered]

    if triggered and (now_epoch - last_notify_epoch) >= float(cooldown_seconds):
        reason = ",".join([f"{k}:{v}/{th}" for k, v, th in triggered])
        recent = []
        if include_recent_alerts:
            lim = max(int(recent_limit), 0)
            if lim > 0:
                tail = alerts[-lim:]
                recent = [_compact_alert(x) for x in tail if isinstance(x, dict)]
        payload = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "date": date_str,
            "broker": broker,
            "status": status,
            "triggered": triggered_items,
            "recent_alerts": recent,
        }

        emit_event("alert.policy", "CRITICAL", "threshold_triggered", reason, payload)
        if auto_kill_switch:
            emit_event("alert.policy", "CRITICAL", "kill_switch_recommended", reason, payload)
        notify_triggered = True

        if webhook_url:
            ok, msg = post_json(webhook_url, payload)
            emit_event(
                "alert.webhook",
                "ERROR" if not ok else "WARN",
                "send_failed" if not ok else "sent",
                msg if msg else ("sent" if ok else "failed"),
                {"url": webhook_url},
            )

        state["last_notify_epoch"] = now_epoch
        state["last_notify_reason"] = reason
    elif triggered and last_notify_reason:
        state["last_notify_reason"] = last_notify_reason

    _save_state(state_path, state)
    return {"triggered": notify_triggered, "reason": reason, "items": triggered_items, "counters": counters}
