import os
import socket
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from config import (
    AGENT_RUN_LOCK_STALE_SECONDS,
    AGENT_SCHEDULER_ENABLED,
    AGENT_SCHEDULE_POLL_SECONDS,
    AGENT_SCHEDULE_TIME,
    AGENT_SCHEDULE_TIMEZONE,
)
from utils.heartbeat import HeartbeatStore, utc_now_z
from utils.logger import setup_logger

logger = setup_logger(__name__)


def parse_schedule_time(value: str) -> tuple[int, int]:
    text = str(value or "").strip()
    hour_text, minute_text = text.split(":", 1)
    hour = int(hour_text)
    minute = int(minute_text)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"invalid schedule time: {value}")
    return hour, minute


def compute_next_run_at(now: datetime, schedule_time: str) -> datetime:
    hour, minute = parse_schedule_time(schedule_time)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now >= target:
        target = target + timedelta(days=1)
    return target


def should_trigger_daily_run(now: datetime, schedule_time: str, last_run_date: str = "") -> bool:
    hour, minute = parse_schedule_time(schedule_time)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    today = now.date().isoformat()
    return now >= target and str(last_run_date or "") != today


def has_active_daily_run(doc: dict) -> bool:
    current = doc.get("current") if isinstance(doc, dict) else None
    if not isinstance(current, dict):
        return False
    return (
        str(current.get("component") or "") == "daily_agent"
        and str(current.get("status") or "") == "running"
    )


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


def _pid_exists(pid: object) -> bool:
    try:
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


def is_stale_active_daily_run(doc: dict, stale_after_seconds: int = AGENT_RUN_LOCK_STALE_SECONDS) -> bool:
    current = doc.get("current") if isinstance(doc, dict) else None
    if not isinstance(current, dict):
        return False
    if str(current.get("component") or "") != "daily_agent":
        return False
    if str(current.get("status") or "") != "running":
        return False

    current_host = str(current.get("host") or "")
    local_host = socket.gethostname()
    current_pid = current.get("pid")
    if current_host and current_host == local_host and current_pid is not None:
        return not _pid_exists(current_pid)

    started_at = _parse_iso_ts(str(current.get("started_at") or ""))
    if started_at is None:
        return False
    age = (datetime.now(timezone.utc) - started_at.astimezone(timezone.utc)).total_seconds()
    return age >= max(int(stale_after_seconds), 60)


def is_already_running_result(result: object) -> bool:
    return isinstance(result, dict) and str(result.get("status") or "") == "already_running"


def resolve_last_run_date(previous_last_run_date: str, trigger_date: str, *, failed: bool) -> str:
    if failed:
        return str(previous_last_run_date or "")
    return str(trigger_date or previous_last_run_date or "")


def main():
    if not AGENT_SCHEDULER_ENABLED:
        logger.warning("⏸️ AGENT_SCHEDULER_ENABLED 未开启；调度器不启动。")
        return

    from run_agent import main as run_daily_agent

    tz = ZoneInfo(AGENT_SCHEDULE_TIMEZONE)
    poll_seconds = max(int(AGENT_SCHEDULE_POLL_SECONDS), 5)
    store = HeartbeatStore()

    logger.info(
        f"🕒 调度器已启动：每天 {AGENT_SCHEDULE_TIMEZONE} {AGENT_SCHEDULE_TIME} 运行一次 daily agent，轮询间隔 {poll_seconds}s。"
    )

    try:
        while True:
            now = datetime.now(tz)
            doc = store.load()
            scheduler = doc.get("scheduler") if isinstance(doc.get("scheduler"), dict) else {}
            last_run_date = str(scheduler.get("last_run_date") or "")
            next_run_at = compute_next_run_at(now, AGENT_SCHEDULE_TIME)
            store.update_scheduler(
                enabled=True,
                loop_status="waiting",
                schedule_time=AGENT_SCHEDULE_TIME,
                timezone=AGENT_SCHEDULE_TIMEZONE,
                poll_seconds=poll_seconds,
                next_run_at=next_run_at.isoformat(),
                last_check_ts=utc_now_z(),
                last_run_date=last_run_date,
                message="scheduler idle",
            )

            if has_active_daily_run(doc):
                if is_stale_active_daily_run(doc):
                    current = doc.get("current") if isinstance(doc.get("current"), dict) else {}
                    store.recover_stale_current(
                        reason="scheduler_detected_stale_current",
                        pid=current.get("pid"),
                        host=current.get("host"),
                    )
                    time.sleep(poll_seconds)
                    continue
                store.update_scheduler(
                    enabled=True,
                    loop_status="blocked",
                    schedule_time=AGENT_SCHEDULE_TIME,
                    timezone=AGENT_SCHEDULE_TIMEZONE,
                    poll_seconds=poll_seconds,
                    next_run_at=next_run_at.isoformat(),
                    last_check_ts=utc_now_z(),
                    last_run_date=last_run_date,
                    message="scheduler blocked: active daily run detected",
                )
                time.sleep(poll_seconds)
                continue

            if should_trigger_daily_run(now, AGENT_SCHEDULE_TIME, last_run_date=last_run_date):
                trigger_date = now.date().isoformat()
                trigger_ts = utc_now_z()
                logger.info(f"🚀 调度器触发本次日常运行：trade_date={trigger_date}")
                store.update_scheduler(
                    enabled=True,
                    loop_status="triggering",
                    schedule_time=AGENT_SCHEDULE_TIME,
                    timezone=AGENT_SCHEDULE_TIMEZONE,
                    poll_seconds=poll_seconds,
                    next_run_at=compute_next_run_at(now, AGENT_SCHEDULE_TIME).isoformat(),
                    last_check_ts=trigger_ts,
                    last_trigger_ts=trigger_ts,
                    last_run_date=last_run_date,
                    message="scheduled run started",
                )
                try:
                    result = run_daily_agent(run_mode="scheduled")
                    recorded_last_run_date = resolve_last_run_date(
                        last_run_date,
                        trigger_date,
                        failed=False,
                    )
                    if is_already_running_result(result):
                        logger.warning("⏸️ 调度器触发时检测到已有运行中的 daily agent，本次不重复启动。")
                        store.update_scheduler(
                            enabled=True,
                            loop_status="blocked",
                            schedule_time=AGENT_SCHEDULE_TIME,
                            timezone=AGENT_SCHEDULE_TIMEZONE,
                            poll_seconds=poll_seconds,
                            next_run_at=compute_next_run_at(datetime.now(tz), AGENT_SCHEDULE_TIME).isoformat(),
                            last_check_ts=utc_now_z(),
                            last_trigger_ts=trigger_ts,
                            last_run_date=recorded_last_run_date,
                            message="scheduled run skipped: already running",
                        )
                    else:
                        logger.info("✅ 调度器本次运行结束。")
                        store.update_scheduler(
                            enabled=True,
                            loop_status="waiting",
                            schedule_time=AGENT_SCHEDULE_TIME,
                            timezone=AGENT_SCHEDULE_TIMEZONE,
                            poll_seconds=poll_seconds,
                            next_run_at=compute_next_run_at(datetime.now(tz), AGENT_SCHEDULE_TIME).isoformat(),
                            last_check_ts=utc_now_z(),
                            last_trigger_ts=trigger_ts,
                            last_run_date=recorded_last_run_date,
                            message="last scheduled run finished",
                        )
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.error(f"❌ 调度器运行失败：{e}", exc_info=True)
                    recorded_last_run_date = resolve_last_run_date(
                        last_run_date,
                        trigger_date,
                        failed=True,
                    )
                    store.update_scheduler(
                        enabled=True,
                        loop_status="error",
                        schedule_time=AGENT_SCHEDULE_TIME,
                        timezone=AGENT_SCHEDULE_TIMEZONE,
                        poll_seconds=poll_seconds,
                        next_run_at=compute_next_run_at(datetime.now(tz), AGENT_SCHEDULE_TIME).isoformat(),
                        last_check_ts=utc_now_z(),
                        last_trigger_ts=trigger_ts,
                        last_run_date=recorded_last_run_date,
                        message=str(e),
                    )

            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        logger.info("🛑 调度器收到停止信号，正在退出。")
        store.update_scheduler(
            enabled=True,
            loop_status="stopped",
            schedule_time=AGENT_SCHEDULE_TIME,
            timezone=AGENT_SCHEDULE_TIMEZONE,
            poll_seconds=poll_seconds,
            next_run_at=None,
            last_check_ts=utc_now_z(),
            message="scheduler stopped by user",
        )


if __name__ == "__main__":
    main()
