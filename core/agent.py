"""MacroQuantAgent: orchestrates the daily routine via injected PlanningService, ExecutionService, PersistenceService, and OpsService."""
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
from execution.broker import BaseBroker
from core.planning import PlanningService, _build_would_submit_preview, get_submission_guard_reason
from core.execution import ExecutionService as ExecutionSvc
from core.persistence import PersistenceService
from core.ops import OpsService
from utils.structlog import log_struct
from utils.trading_hours import get_market_session


class MacroQuantAgent:
    def __init__(
        self,
        llm_client,
        retriever,
        broker: BaseBroker,
        run_mode: str = "manual",
        planning_service: Optional[PlanningService] = None,
        execution_service: Optional[ExecutionSvc] = None,
        persistence_service: Optional[PersistenceService] = None,
        ops_service: Optional[OpsService] = None,
    ):
        self.llm = llm_client
        self.retriever = retriever
        self.broker = broker
        self.run_mode = str(run_mode or "manual")
        self._planning = planning_service
        self._execution = execution_service
        self._persistence = persistence_service
        self._ops = ops_service
        self.cash, self.positions = self.broker.get_account_summary()

    def run_daily_routine(self):
        date_str = datetime.now(ZoneInfo(MARKET_TIMEZONE)).date().isoformat()
        t0 = time.perf_counter()
        status = "unknown"
        fatal_error = None
        metrics = {"date": date_str, "broker": BROKER_TYPE, "run_mode": self.run_mode}

        ops = self._ops
        persistence = self._persistence
        planning = self._planning
        execution = self._execution

        heartbeat_run = ops.start_run(
            run_mode=self.run_mode,
            date_str=date_str,
            broker=BROKER_TYPE,
            live_trading_enabled=bool(ENABLE_LIVE_TRADING),
        )
        run_start_ts = str(heartbeat_run.get("started_at") or (datetime.utcnow().isoformat() + "Z"))
        metrics["run_start_ts"] = run_start_ts
        metrics["live_trading_enabled"] = bool(ENABLE_LIVE_TRADING)

        try:
            if self._is_kill_switch_locked(ops, date_str):
                status = "kill_switch_locked"
                return

            market_session = self._resolve_market_session(metrics)
            if self._is_market_closed(market_session):
                self._persist_market_closed(persistence, date_str, market_session, run_start_ts)
                status = "market_closed"
                return

            ctx = self._retrieve_and_persist_context(planning, persistence, date_str, metrics, market_session)
            if ctx is None:
                status = "abort_no_prices"
                return

            plan_result = self._generate_plan(planning, ctx, date_str, metrics)
            if self._handle_plan_gate(plan_result, persistence, ctx, date_str, market_session, run_start_ts):
                status = "invalid"
                return

            proposed_orders = self._apply_plan_metrics(plan_result, metrics)
            if self._is_no_trade(plan_result):
                self._persist_no_trade(persistence, plan_result, ctx, date_str, market_session, run_start_ts)
                status = "no_trade"
                return

            if self._try_planning_only_gate(ops, persistence, proposed_orders, plan_result, ctx, date_str, run_start_ts, metrics):
                status = "planning_only"
                return

            exec_status = self._execute_and_persist(execution, persistence, proposed_orders, plan_result, ctx, date_str, run_start_ts, metrics)
            status = exec_status or "traded"

        except Exception as e:
            fatal_error = str(e)
            ops.trigger_kill_switch(str(e), source="agent.exception", trigger_event={"date": date_str, "broker": BROKER_TYPE, "run_mode": self.run_mode})
            logger.error(f"致命错误，已熔断: {e}")
            logger.exception("异常堆栈详情：")
            status = "exception"
            raise
        finally:
            self._finalize_run(ops, persistence, heartbeat_run, status, fatal_error, metrics, date_str, t0, run_start_ts)

    def _is_kill_switch_locked(self, ops, date_str) -> bool:
        ks = ops.check_kill_switch()
        if ks["locked"]:
            logger.error(f"熔断已锁定: {ks['reason']}")
            log_struct("kill_switch_locked", {"date": date_str, "broker": BROKER_TYPE, "run_mode": self.run_mode, "kill_switch_reason": ks["reason"]}, level="WARNING")
            return True
        return False

    def _resolve_market_session(self, metrics) -> dict:
        market_session = get_market_session(
            datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")),
            MARKET_TIMEZONE,
            RTH_START,
            RTH_END,
            HALF_DAY_RTH_END,
        )
        metrics["market_state"] = market_session.get("market_state")
        metrics["market_reason"] = market_session.get("session_reason")
        metrics["trading_day"] = bool(market_session.get("is_trading_day"))
        metrics["market_half_day"] = bool(market_session.get("is_half_day"))
        metrics["market_rth_end"] = market_session.get("effective_rth_end")
        log_struct("daily_start", {"date": metrics["date"], "broker": BROKER_TYPE, "market_state": market_session.get("market_state"), "session_reason": market_session.get("session_reason")})
        return market_session

    def _is_market_closed(self, market_session) -> bool:
        return market_session.get("market_state") == "closed"

    def _persist_market_closed(self, persistence, date_str, market_session, run_start_ts):
        reason = str(market_session.get("session_reason") or "closed")
        logger.info(f"市场休市（{reason}），今日不生成新策略。")
        self._ops.emit_event("market.session", "INFO", "closed", reason, {"date": date_str})
        log_struct("market_closed", {"date": date_str, "broker": BROKER_TYPE, "reason": reason})
        persistence.save_decision_snapshot(date_str, {
            "status": "market_closed",
            "reasoning": f"市场休市（{reason}）",
            "plan": {},
            "orders": [],
            "positions_after": self.positions,
            "cash_after": self.cash,
            "market_session": market_session,
            "run_start_ts": run_start_ts,
        })

    def _retrieve_and_persist_context(self, planning, persistence, date_str, metrics, market_session) -> Optional[dict]:
        ctx = planning.retrieve_context(
            cash=float(self.cash),
            positions={k: float(v) for k, v in self.positions.items()},
            market_session=market_session,
            date_str=date_str,
            run_mode=self.run_mode,
        )
        if not ctx.get("success"):
            logger.warning("RAG 检索失败（无价格），跳过调仓。")
            log_struct("daily_abort_no_prices", {"date": date_str, "broker": BROKER_TYPE}, level="WARNING")
            return None

        metrics["rag_sec"] = ctx["rag_sec"]
        metrics["provider_status"] = ctx["provider_status"]

        persistence.save_rag_snapshot(date_str, {
            "macro": ctx["macro_data"],
            "fundamental": ctx["fundamental_data"],
            "news": ctx["news_data"],
            "market": ctx["market_data_dict"],
            "filings": ctx["filing_data"],
            "provider_status": ctx["provider_status"],
            "retrieval_route": ctx["retrieval_route"],
        })
        return ctx

    def _generate_plan(self, planning, ctx, date_str, metrics) -> dict:
        plan_result = planning.generate_plan(
            cash=float(self.cash),
            positions={k: float(v) for k, v in self.positions.items()},
            ctx=ctx,
            date_str=date_str,
            run_mode=self.run_mode,
        )

        metrics["llm_sec"] = plan_result["llm_sec"]
        pll_audit = (plan_result.get("llm_audit") or {})
        metrics["llm_valid"] = bool(pll_audit.get("prompt_version"))
        metrics["prompt_version"] = pll_audit.get("prompt_version")
        metrics["strategy_ids"] = (plan_result.get("strategy_ids") or [])
        metrics["cash_ratio"] = plan_result.get("cash_ratio", 0.0)
        metrics["llm_errors"] = plan_result.get("errors", [])
        metrics["llm_warning_count"] = len(plan_result.get("warnings", []))
        if plan_result.get("rebalance_sec") is not None:
            metrics["rebalance_sec"] = plan_result["rebalance_sec"]
        return plan_result

    def _handle_plan_gate(self, plan_result, persistence, ctx, date_str, market_session, run_start_ts) -> bool:
        if plan_result["status"] != "invalid":
            return False
        logger.error("LLM 校验失败，跳过调仓。")
        persistence.save_decision_snapshot(date_str, {
            "status": "invalid",
            "reasoning": plan_result["reasoning"],
            "plan": plan_result["plan_snapshot"],
            "llm_audit": plan_result["llm_audit"],
            "retrieval_route": ctx["retrieval_route"],
            "orders": [],
            "positions_after": self.positions,
            "cash_after": self.cash,
            "market_session": market_session,
            "run_start_ts": run_start_ts,
            "decision_prices": ctx["current_prices"],
        })
        return True

    def _apply_plan_metrics(self, plan_result, metrics) -> list:
        proposed_orders = plan_result.get("proposed_orders", [])
        metrics["order_count"] = len(proposed_orders)
        metrics["turnover"] = plan_result.get("turnover_ratio", 0.0)
        return proposed_orders

    def _is_no_trade(self, plan_result) -> bool:
        return plan_result["status"] == "no_trade"

    def _persist_no_trade(self, persistence, plan_result, ctx, date_str, market_session, run_start_ts):
        logger.info("仓位已达标，无需调仓。")
        persistence.save_decision_snapshot(date_str, {
            "status": "no_trade",
            "reasoning": plan_result["reasoning"],
            "plan": plan_result["plan_snapshot"],
            "llm_audit": plan_result["llm_audit"],
            "retrieval_route": ctx["retrieval_route"],
            "orders": [],
            "positions_after": self.positions,
            "cash_after": self.cash,
            "market_session": market_session,
            "run_start_ts": run_start_ts,
            "decision_prices": ctx["current_prices"],
        })

    def _get_execution_guard_reason(self, market_session_recheck) -> Optional[str]:
        metrics_rth_ok = bool(market_session_recheck.get("can_place_orders"))
        if ENFORCE_RTH and not ALLOW_OUTSIDE_RTH and not metrics_rth_ok:
            return str(market_session_recheck.get("session_reason") or "out_of_window")
        return get_submission_guard_reason(BROKER_TYPE, ENABLE_LIVE_TRADING)

    def _try_planning_only_gate(self, ops, persistence, proposed_orders, plan_result, ctx, date_str, run_start_ts, metrics) -> bool:
        market_session_recheck = get_market_session(
            datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")),
            MARKET_TIMEZONE,
            RTH_START,
            RTH_END,
            HALF_DAY_RTH_END,
        )
        metrics["rth_ok"] = bool(market_session_recheck.get("can_place_orders"))

        planning_reason = self._get_execution_guard_reason(market_session_recheck)
        if not planning_reason:
            self._market_session_recheck = market_session_recheck
            return False

        would_submit_preview = _build_would_submit_preview(proposed_orders, market_session=market_session_recheck)
        logger.warning(f"仅生成计划，不下单（{planning_reason}）。")
        ops.emit_event("agent", "WARN", "planning_only", planning_reason, {"date": date_str})
        log_struct("planning_only", {"date": date_str, "broker": BROKER_TYPE, "reason": planning_reason}, level="WARNING")
        persistence.save_decision_snapshot(date_str, {
            "status": "planning_only",
            "reasoning": plan_result["reasoning"],
            "plan": plan_result["plan_snapshot"],
            "llm_audit": plan_result["llm_audit"],
            "retrieval_route": ctx["retrieval_route"],
            "orders": proposed_orders,
            "would_submit_preview": would_submit_preview,
            "positions_after": self.positions,
            "cash_after": self.cash,
            "market_session": market_session_recheck,
            "planning_only_reason": planning_reason,
            "live_trading_enabled": bool(ENABLE_LIVE_TRADING),
            "run_start_ts": run_start_ts,
            "decision_prices": ctx["current_prices"],
        })
        return True

    def _execute_and_persist(self, execution, persistence, proposed_orders, plan_result, ctx, date_str, run_start_ts, metrics):
        market_session_recheck = getattr(self, "_market_session_recheck", None) or get_market_session(
            datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")),
            MARKET_TIMEZONE,
            RTH_START,
            RTH_END,
            HALF_DAY_RTH_END,
        )
        if "rth_ok" not in metrics:
            metrics["rth_ok"] = bool(market_session_recheck.get("can_place_orders"))

        before_cash = float(self.cash)
        before_positions = dict(self.positions)

        exec_result = execution.execute(
            orders=proposed_orders,
            before_cash=before_cash,
            before_positions=before_positions,
        )

        self.cash, self.positions = float(exec_result["after_cash"]), dict(exec_result["after_positions"])
        metrics["submit_sec"] = exec_result["submit_sec"]
        metrics["reconcile_sec"] = exec_result["reconcile_sec"]
        metrics["reconcile_ok"] = exec_result["reconcile_ok"]

        logger.info(f"调仓完毕！最新现金: ${self.cash:,.2f}")
        logger.info(f"最新持仓: {self.positions}")
        persistence.save_portfolio_state(float(self.cash), dict(self.positions))

        if exec_result["reconcile_ok"]:
            log_struct("reconcile_ok", {"date": date_str, "broker": BROKER_TYPE})
        else:
            logger.warning(f"对账差异: {exec_result['reconciliation'].get('mismatched')}")
            log_struct("reconcile_mismatch", {"date": date_str, "broker": BROKER_TYPE, "mismatched": exec_result["reconciliation"].get("mismatched")}, level="WARNING")

        persistence.save_execution_ledger(date_str, {
            "before": {"cash": before_cash, "positions": before_positions},
            "orders": proposed_orders,
            "execution_report": exec_result["execution_report"],
            "after": {"cash": self.cash, "positions": self.positions},
            "reconciliation": exec_result["reconciliation"],
        })

        persistence.save_decision_snapshot(date_str, {
            "status": exec_result["execution_summary"].get("status"),
            "reasoning": plan_result["reasoning"],
            "plan": plan_result["plan_snapshot"],
            "llm_audit": plan_result["llm_audit"],
            "retrieval_route": ctx["retrieval_route"],
            "orders": proposed_orders,
            "execution_report": exec_result["execution_report"],
            "execution_summary": exec_result["execution_summary"],
            "reconciliation": exec_result["reconciliation"],
            "positions_after": self.positions,
            "cash_after": self.cash,
            "market_session": market_session_recheck,
            "run_start_ts": run_start_ts,
            "decision_prices": ctx["current_prices"],
        })

        metrics["status"] = exec_result["execution_summary"].get("status") or "traded"
        return metrics["status"]

    def _finalize_run(self, ops, persistence, heartbeat_run, status, fatal_error, metrics, date_str, t0, run_start_ts):
        run_end_ts = datetime.utcnow().isoformat() + "Z"
        metrics["status"] = status
        metrics["total_sec"] = round(time.perf_counter() - t0, 6)
        metrics["run_end_ts"] = run_end_ts
        ops.finish_run(
            str(heartbeat_run.get("run_id") or ""),
            status=status,
            error=fatal_error,
            extra={"date": date_str, "broker": BROKER_TYPE, "run_mode": self.run_mode, "live_trading_enabled": bool(ENABLE_LIVE_TRADING), "market_state": metrics.get("market_state"), "total_sec": metrics.get("total_sec")},
        )
        if metrics.get("date") is not None:
            persistence.append_metrics(metrics)
            decision = persistence.load_decision_snapshot(str(metrics.get("date")))
            notify_result = ops.evaluate_and_notify(
                date_str=str(metrics.get("date")),
                broker=BROKER_TYPE,
                status=str(metrics.get("status")),
                run_start_ts=str(metrics.get("run_start_ts")),
                run_end_ts=str(metrics.get("run_end_ts")),
                webhook_url=(ALERT_WEBHOOK_URL or None),
                cooldown_seconds=int(ALERT_COOLDOWN_SECONDS),
                thresholds={
                    "data_failed": int(ALERT_DATA_FAILED_THRESHOLD),
                    "llm_invalid": int(ALERT_LLM_INVALID_THRESHOLD),
                    "order_problem": int(ALERT_ORDER_PROBLEM_THRESHOLD),
                    "exception": int(ALERT_EXCEPTION_THRESHOLD),
                },
                auto_kill_switch=bool(ALERT_AUTO_KILL_SWITCH),
                include_recent_alerts=bool(ALERT_WEBHOOK_INCLUDE_RECENT),
                recent_limit=int(ALERT_WEBHOOK_RECENT_LIMIT),
            )
            if bool(ALERT_AUTO_KILL_SWITCH) and notify_result.get("triggered"):
                reason = notify_result.get("reason") or "alert_policy_triggered"
                if decision and isinstance(decision, dict):
                    merged = dict(decision.get("payload") or {})
                    merged["kill_switch_reason"] = reason
                    persistence.save_decision_snapshot(str(metrics.get("date")), merged)
                ops.trigger_kill_switch(f"alert_policy:{reason}", source="alert.policy", trigger_event={"date": str(metrics.get("date")), "broker": BROKER_TYPE, "status": str(metrics.get("status")), "policy_items": notify_result.get("items")})
