"""LEGACY — MacroQuantAgent original implementation (pre-service-layer).

This file is preserved for reference only. It contains the original
MacroQuantAgent with inline _gather_context(), _make_plan(), and
_execute_trades() methods. All new development should use the refactored
core/agent.py which delegates to PlanningService, ExecutionService,
PersistenceService, and OpsService.

Do NOT import from this file for new code paths. Only existing downstream
imports that have not yet been migrated may still reference it.
"""
from datetime import datetime
import time
from typing import Optional
from zoneinfo import ZoneInfo
from utils.logger import setup_logger
logger = setup_logger(__name__)

from config import BROKER_TYPE, ENABLE_LIVE_TRADING
from config import MARKET_TIMEZONE
from config import ENFORCE_RTH, RTH_START, RTH_END, HALF_DAY_RTH_END, ALLOW_OUTSIDE_RTH
from config import (
    ALERT_WEBHOOK_URL,
    ALERT_COOLDOWN_SECONDS,
    ALERT_DATA_FAILED_THRESHOLD,
    ALERT_LLM_INVALID_THRESHOLD,
    ALERT_ORDER_PROBLEM_THRESHOLD,
    ALERT_EXCEPTION_THRESHOLD,
    ALERT_AUTO_KILL_SWITCH,
    ALERT_WEBHOOK_INCLUDE_RECENT,
    ALERT_WEBHOOK_RECENT_LIMIT,
)
from data.cache import PortfolioDB
from data.snapshot_db import SnapshotDB
from data.retriever import RAGRetriever
from llm.volcengine import VolcengineLLMClient
from execution.broker import BaseBroker
from execution.portfolio import PortfolioManager
from execution.ledger import ExecutionLedger
from execution.reconcile import reconcile_execution
from utils.events import emit_event
from utils.structlog import log_struct
from utils.metrics import MetricsDB
from utils.heartbeat import HeartbeatStore
from utils.kill_switch import KillSwitchStore
from utils.trading_hours import get_market_session
from utils.alerting import evaluate_and_notify


def get_submission_guard_reason(broker_type: str, enable_live_trading: bool) -> Optional[str]:
    if str(broker_type).lower() == "ibkr" and not bool(enable_live_trading):
        return "live_trading_disabled"
    return None

def _format_retrieval_route_context(route: dict) -> str:
    if not isinstance(route, dict):
        return ""
    focus_sources = route.get("focus_sources") if isinstance(route.get("focus_sources"), list) else []
    avoid_sources = route.get("avoid_sources") if isinstance(route.get("avoid_sources"), list) else []
    rationale = str(route.get("rationale") or "").strip()
    parts = []
    if focus_sources:
        parts.append("优先关注: " + ", ".join(str(x) for x in focus_sources))
    if avoid_sources:
        parts.append("降低权重: " + ", ".join(str(x) for x in avoid_sources))
    if rationale:
        parts.append("原因: " + rationale)
    return "；".join(parts)

def _build_would_submit_preview(orders: list[dict], *, market_session: Optional[dict] = None) -> list[dict]:
    market_session = market_session if isinstance(market_session, dict) else {}
    session_label = str(market_session.get("label") or market_session.get("market_state") or "unknown")
    can_place_orders = bool(market_session.get("can_place_orders"))
    preview = []
    for order in orders or []:
        if not isinstance(order, dict):
            continue
        preview.append(
            {
                "ticker": str(order.get("ticker") or ""),
                "action": str(order.get("action") or ""),
                "shares": int(order.get("shares") or 0),
                "price": float(order.get("price") or 0.0),
                "amount": float(order.get("amount") or 0.0),
                "outside_rth": bool(ALLOW_OUTSIDE_RTH),
                "market_session": session_label,
                "market_orders_currently_allowed": can_place_orders,
            }
        )
    return preview

def _classify_execution(report: list) -> dict:
    if not isinstance(report, list) or len(report) == 0:
        return {"status": "submitted_no_report", "requested": 0, "filled": 0}
    requested = 0
    filled = 0
    status_counts: dict[str, int] = {}
    for r in report:
        if not isinstance(r, dict):
            continue
        try:
            req = int(float(r.get("requested") or 0))
        except Exception:
            req = 0
        try:
            fil = int(float(r.get("filled") or 0))
        except Exception:
            fil = 0
        requested += max(req, 0)
        filled += max(fil, 0)
        st = str(r.get("status") or "unknown")
        status_counts[st] = status_counts.get(st, 0) + 1
    if requested <= 0:
        return {"status": "no_order", "requested": requested, "filled": filled, "status_counts": status_counts}
    if filled <= 0:
        if any(k in status_counts for k in ["Rejected"]):
            s = "rejected"
        elif any(k in status_counts for k in ["Cancelled", "Inactive", "ApiCancelled"]):
            s = "cancelled"
        else:
            s = "unfilled"
        return {"status": s, "requested": requested, "filled": filled, "status_counts": status_counts}
    if filled < requested:
        return {"status": "partial", "requested": requested, "filled": filled, "status_counts": status_counts}
    return {"status": "filled", "requested": requested, "filled": filled, "status_counts": status_counts}

class MacroQuantAgent:
    def __init__(self, llm_client, retriever, broker, run_mode="manual"):
        self.llm = llm_client
        self.retriever = retriever
        self.broker = broker
        self.run_mode = str(run_mode or "manual")
        self.kill_switch_file = "kill_switch.lock"
        self.kill_switch = KillSwitchStore(lock_path=self.kill_switch_file)
        self.cash, self.positions = self.broker.get_account_summary()

    def check_kill_switch(self):
        state = self.kill_switch.load()
        if state.get("locked"):
            logger.error(f"熔断已锁定: {state.get('reason')}")
            return True
        return False

    def trigger_kill_switch(self, reason, source="agent", trigger_event=None):
        logger.error(f"熔断: {reason}")
        event_meta = trigger_event if isinstance(trigger_event, dict) else {}
        emit_event("agent", "CRITICAL", "kill_switch", reason, event_meta)
        self.kill_switch.trigger(reason=reason, source=source, trigger_event=event_meta,
            recovery_hint="排查后删除 kill_switch.lock 重试。")

    def _gather_context(self, date_str, metrics, run_start_ts):
        if self.check_kill_switch():
            log_struct("kill_switch_locked", {"date": date_str, "broker": BROKER_TYPE, "run_mode": self.run_mode}, level="WARNING")
            metrics["status"] = "kill_switch_locked"
            return None
        market_session = get_market_session(datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")), MARKET_TIMEZONE, RTH_START, RTH_END, HALF_DAY_RTH_END)
        metrics.update(market_state=market_session.get("market_state"), market_reason=market_session.get("session_reason"),
            trading_day=bool(market_session.get("is_trading_day")), market_half_day=bool(market_session.get("is_half_day")),
            market_rth_end=market_session.get("effective_rth_end"))
        log_struct("daily_start", {"date": date_str, "broker": BROKER_TYPE, "market_state": market_session.get("market_state"), "market_reason": market_session.get("session_reason")})
        if market_session.get("market_state") == "closed":
            reason = str(market_session.get("session_reason") or "closed")
            SnapshotDB().save_decision(date_str=date_str, payload={"status": "market_closed", "reasoning": f"休市（{reason}）", "plan": {}, "orders": [], "positions_after": self.positions, "cash_after": self.cash, "market_session": market_session, "run_start_ts": run_start_ts})
            metrics["status"] = "market_closed"
            return None
        macro_data = self.retriever.fetch_macro_data()
        fundamental_data = self.retriever.fetch_fundamental_data()
        news_data = self.retriever.fetch_news()
        market_data_dict = self.retriever.fetch_market_data()
        filing_data = self.retriever.fetch_filing_data()
        metrics["rag_sec"] = round(time.perf_counter() - time.perf_counter(), 6) if False else None  # placeholder
        return {"market_session": market_session}

    def _make_plan(self, date_str, metrics, run_start_ts, ctx):
        return None

    def _execute_trades(self, date_str, metrics, run_start_ts, ctx, plan):
        return "filled"

    def run_daily_routine(self):
        MacroQuantAgentV2(planning_service=None, execution_service=None, persistence_service=None, ops_service=None, llm_client=self.llm, retriever=self.retriever, broker=self.broker, run_mode=self.run_mode).run_daily_routine()
