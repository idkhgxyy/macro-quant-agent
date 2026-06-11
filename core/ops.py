"""OpsService: heartbeat, kill switch, alerting, and event emission.

Extracted from MacroQuantAgent.trigger_kill_switch() and the
run_daily_routine() finally block. Stateless: each method instantiates
its own store or calls the relevant utility.
"""
from typing import Optional

from utils.alerting import evaluate_and_notify
from utils.events import emit_event
from utils.heartbeat import HeartbeatStore
from utils.kill_switch import KillSwitchStore


class OpsService:
    """Runtime operations: lifecycle tracking, circuit-breaker, alerts, events."""

    @staticmethod
    def start_run(run_mode: str, date_str: str, broker: str, live_trading_enabled: bool) -> dict:
        return HeartbeatStore().start_run(
            run_mode=run_mode,
            date_str=date_str,
            broker=broker,
            live_trading_enabled=live_trading_enabled,
        )

    @staticmethod
    def finish_run(run_id: str, status: str, error: Optional[str] = None, extra: Optional[dict] = None) -> None:
        HeartbeatStore().finish_run(run_id=run_id, status=status, error=error, extra=extra)

    @staticmethod
    def check_kill_switch(lock_path: str = "kill_switch.lock") -> dict:
        state = KillSwitchStore(lock_path=lock_path).load()
        if state.get("locked"):
            return {
                "locked": True,
                "reason": str(state.get("reason") or "unknown"),
                "source": str(state.get("source") or "unknown"),
            }
        return {"locked": False}

    @staticmethod
    def trigger_kill_switch(
        reason: str,
        source: str = "agent",
        trigger_event: Optional[dict] = None,
        lock_path: str = "kill_switch.lock",
    ) -> None:
        event_meta = trigger_event if isinstance(trigger_event, dict) else {}
        emit_event("agent", "CRITICAL", "kill_switch", reason, event_meta)
        KillSwitchStore(lock_path=lock_path).trigger(
            reason=reason,
            source=source,
            trigger_event=event_meta,
            recovery_hint="排查异常、确认问题已解除后删除 kill_switch.lock，再重新启动 daily agent 或 scheduler。",
        )

    @staticmethod
    def emit_event(category: str, severity: str, kind: str, message: str, meta: Optional[dict] = None) -> None:
        emit_event(category, severity, kind, message, meta)

    @staticmethod
    def evaluate_and_notify(
        date_str: str,
        broker: str,
        status: str,
        run_start_ts: str,
        run_end_ts: str,
        webhook_url: Optional[str] = None,
        cooldown_seconds: int = 300,
        thresholds: Optional[dict] = None,
        auto_kill_switch: bool = False,
        include_recent_alerts: bool = False,
        recent_limit: int = 5,
    ) -> dict:
        return evaluate_and_notify(
            date_str=date_str,
            broker=broker,
            status=status,
            run_start_ts=run_start_ts,
            run_end_ts=run_end_ts,
            webhook_url=webhook_url,
            cooldown_seconds=cooldown_seconds,
            thresholds=thresholds or {},
            auto_kill_switch=auto_kill_switch,
            include_recent_alerts=include_recent_alerts,
            recent_limit=recent_limit,
        )
