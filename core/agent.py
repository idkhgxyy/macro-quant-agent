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


class MacroQuantAgent:
    """系统的核心组装器：调度 Data、LLM 和 Execution 层"""
    def __init__(
        self,
        llm_client: VolcengineLLMClient,
        retriever: RAGRetriever,
        broker: BaseBroker,
        run_mode: str = "manual",
    ):
        self.llm = llm_client
        self.retriever = retriever
        self.broker = broker
        self.run_mode = str(run_mode or "manual")
        self.kill_switch_file = "kill_switch.lock"
        self.kill_switch = KillSwitchStore(lock_path=self.kill_switch_file)
        
        # 每天运行时，首先从券商拉取真实账本
        self.cash, self.positions = self.broker.get_account_summary()
        
    def check_kill_switch(self):
        """检查全局熔断锁文件"""
        state = self.kill_switch.load()
        if state.get("locked"):
            reason = state.get("reason") or "unknown"
            source = state.get("source") or "unknown"
            logger.error(
                f"🛑 [全局熔断] 检测到 {self.kill_switch_file} 文件，系统已被锁死！原因: {reason}，来源: {source}。请人工排查问题后手动删除该文件恢复运行。"
            )
            return True
        return False
        
    def trigger_kill_switch(self, reason: str, source: str = "agent", trigger_event: Optional[dict] = None):
        """触发全局熔断，写入锁文件"""
        logger.error(f"🛑 [触发熔断] 发生严重异常：{reason}！系统正在锁定...")
        event_meta = trigger_event if isinstance(trigger_event, dict) else {}
        emit_event("agent", "CRITICAL", "kill_switch", reason, event_meta)
        self.kill_switch.trigger(
            reason=reason,
            source=source,
            trigger_event=event_meta,
            recovery_hint="排查异常、确认问题已解除后删除 kill_switch.lock，再重新启动 daily agent 或 scheduler。",
        )

    def run_daily_routine(self):
        date_str = datetime.now(ZoneInfo(MARKET_TIMEZONE)).date().isoformat()
        t0 = time.perf_counter()
        status = "unknown"
        fatal_error = None
        metrics = {"date": date_str, "broker": BROKER_TYPE, "run_mode": self.run_mode}
        heartbeat_store = HeartbeatStore()
        heartbeat_run = heartbeat_store.start_run(
            run_mode=self.run_mode,
            date_str=date_str,
            broker=BROKER_TYPE,
            live_trading_enabled=bool(ENABLE_LIVE_TRADING),
        )
        run_start_ts = str(heartbeat_run.get("started_at") or (datetime.utcnow().isoformat() + "Z"))
        metrics["run_start_ts"] = run_start_ts
        metrics["live_trading_enabled"] = bool(ENABLE_LIVE_TRADING)
        market_session = None

        try:
            # 0. 熔断检查
            if self.check_kill_switch():
                status = "kill_switch_locked"
                log_struct(
                    "kill_switch_locked",
                    {
                        "date": date_str,
                        "broker": BROKER_TYPE,
                        "run_mode": self.run_mode,
                        "kill_switch_reason": self.kill_switch.load().get("reason"),
                    },
                    level="WARNING",
                )
                return

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
            log_struct(
                "daily_start",
                {
                    "date": date_str,
                    "broker": BROKER_TYPE,
                    "market_state": market_session.get("market_state"),
                    "market_reason": market_session.get("session_reason"),
                    "holiday_name": market_session.get("holiday_name"),
                    "early_close_name": market_session.get("early_close_name"),
                },
            )

            if market_session.get("market_state") == "closed":
                reason = str(market_session.get("session_reason") or "closed")
                logger.info(f"📭 市场休市（{reason}），今日不生成新策略。")
                emit_event(
                    "market.session",
                    "INFO",
                    "closed",
                    reason,
                    {
                        "date": date_str,
                        "holiday_name": market_session.get("holiday_name"),
                        "early_close_name": market_session.get("early_close_name"),
                    },
                )
                log_struct(
                    "market_closed",
                    {
                        "date": date_str,
                        "broker": BROKER_TYPE,
                        "reason": reason,
                        "holiday_name": market_session.get("holiday_name"),
                    },
                )
                status = "market_closed"
                SnapshotDB().save_decision(
                    date_str=date_str,
                    payload={
                        "status": "market_closed",
                        "reasoning": f"市场休市（{reason}），今日不生成新策略。",
                        "plan": {},
                        "orders": [],
                        "positions_after": self.positions,
                        "cash_after": self.cash,
                        "market_session": market_session,
                        "run_start_ts": run_start_ts,
                    },
                )
                return

            # 1. RAG 检索阶段
            t_rag0 = time.perf_counter()
            macro_data = self.retriever.fetch_macro_data()
            fundamental_data = self.retriever.fetch_fundamental_data()
            news_data = self.retriever.fetch_news()
            market_data_dict = self.retriever.fetch_market_data()
            metrics["rag_sec"] = round(time.perf_counter() - t_rag0, 6)
            provider_status = self.retriever.get_provider_status()
            metrics["provider_status"] = provider_status
            log_struct("rag_provider_status", provider_status)
            
            market_context_str = market_data_dict["context_string"]
            current_prices = market_data_dict["prices"]
            
            if not current_prices:
                logger.warning("❌ 无法获取最新价格，今日暂停调仓。")
                log_struct("daily_abort_no_prices", {"date": date_str, "broker": BROKER_TYPE}, level="WARNING")
                status = "abort_no_prices"
                return

            SnapshotDB().save_rag(
                date_str=date_str,
                payload={
                    "macro": macro_data,
                    "fundamental": fundamental_data,
                    "news": news_data,
                    "market": market_data_dict,
                    "provider_status": provider_status,
                },
            )
                
            # 组装当前持仓信息喂给 LLM
            portfolio_value = self.cash
            for ticker, shares in self.positions.items():
                portfolio_value += shares * current_prices.get(ticker, 0)
            
            current_summary = [f"现金: ${self.cash:,.2f} ({self.cash/portfolio_value*100:.1f}%)"]
            for ticker, shares in self.positions.items():
                val = shares * current_prices.get(ticker, 0)
                weight = val / portfolio_value if portfolio_value > 0 else 0
                current_summary.append(f"{ticker}: {shares}股, 价值 ${val:,.2f} ({weight*100:.1f}%)")
            current_positions_str = "\n".join(current_summary)
                
            logger.info("-" * 60)
            logger.info("📂 【RAG 组装完毕的小抄资料】")
            logger.info(f"【当前持仓】:\n{current_positions_str}\n")
            logger.info(f"【宏观数据】:\n{macro_data}\n")
            logger.info(f"【基本面数据】:\n{fundamental_data}\n")
            logger.info(f"【市场数据】:\n{market_context_str}\n")
            logger.info(f"【新闻摘要】:\n{news_data[:200]}...\n")
            logger.info("-" * 60)
            
            # 2. 增强生成阶段
            t_llm0 = time.perf_counter()
            strategy_plan = self.llm.generate_strategy(news_data, market_context_str, macro_data, fundamental_data, current_positions_str)
            metrics["llm_sec"] = round(time.perf_counter() - t_llm0, 6)
                
            # 3. 解析结果
            reasoning = strategy_plan.get("reasoning", "无理由")
            target_weights = strategy_plan.get("allocations", {})
            is_valid = strategy_plan.get("_valid", True)
            errors = strategy_plan.get("_errors", [])
            warnings = strategy_plan.get("_warnings", [])
            strategy_ids = strategy_plan.get("selected_strategies", [])
            llm_audit = strategy_plan.get("_audit", {}) if isinstance(strategy_plan.get("_audit", {}), dict) else {}
            plan_snapshot = {k: v for k, v in strategy_plan.items() if not str(k).startswith("_")}
            cash_ratio = self.cash / portfolio_value if portfolio_value > 0 else 0.0
            metrics["llm_valid"] = bool(is_valid)
            metrics["llm_errors"] = errors
            metrics["llm_warning_count"] = len(warnings) if isinstance(warnings, list) else 0
            metrics["prompt_version"] = llm_audit.get("prompt_version")
            metrics["strategy_ids"] = strategy_ids if isinstance(strategy_ids, list) else []
            metrics["cash_ratio"] = round(cash_ratio, 6)
            log_struct(
                "llm_plan",
                {
                    "date": date_str,
                    "broker": BROKER_TYPE,
                    "cash_ratio": round(cash_ratio, 6),
                    "strategy_ids": strategy_ids if isinstance(strategy_ids, list) else [],
                    "valid": bool(is_valid),
                    "errors": errors,
                    "warnings": warnings,
                    "prompt_version": llm_audit.get("prompt_version"),
                    "model_endpoint": llm_audit.get("model_endpoint"),
                },
            )
            
            logger.info("\n💡 [LLM 策略报告]")
            logger.info(f"逻辑推演: {reasoning}")
            logger.info(f"目标权重: {target_weights}")
            logger.info("-" * 60)

            if not is_valid:
                logger.error(f"🛑 [策略降级] LLM 输出未通过校验，今日暂停调仓。错误: {errors}")
                log_struct("llm_invalid_skip_trade", {"date": date_str, "broker": BROKER_TYPE, "errors": errors}, level="WARNING")
                status = "invalid"
                SnapshotDB().save_decision(
                    date_str=date_str,
                    payload={
                        "status": "invalid",
                        "reasoning": reasoning,
                        "plan": plan_snapshot,
                        "llm_audit": llm_audit,
                        "orders": [],
                        "positions_after": self.positions,
                        "cash_after": self.cash,
                        "market_session": market_session,
                        "run_start_ts": run_start_ts,
                    },
                )
                return
            
            # 4. 执行动态调仓 (Rebalancing)
            t_reb0 = time.perf_counter()
            proposed_orders = PortfolioManager.rebalance(self.cash, self.positions, target_weights, current_prices)
            metrics["rebalance_sec"] = round(time.perf_counter() - t_reb0, 6)
            turnover_ratio = 0.0
            if portfolio_value > 0:
                turnover_ratio = sum([float(o.get("amount", 0.0) or 0.0) for o in proposed_orders]) / float(portfolio_value)
            metrics["turnover"] = round(turnover_ratio, 6)
            metrics["order_count"] = len(proposed_orders)
            log_struct(
                "orders_built",
                {
                    "date": date_str,
                    "broker": BROKER_TYPE,
                    "order_count": len(proposed_orders),
                    "turnover": round(turnover_ratio, 6),
                    "cash_ratio": round(cash_ratio, 6),
                },
            )
            
            if not proposed_orders:
                logger.info("  -> 仓位已达标，今日无需调仓。")
                log_struct("no_trade", {"date": date_str, "broker": BROKER_TYPE, "cash_ratio": round(cash_ratio, 6)})
                status = "no_trade"
                SnapshotDB().save_decision(
                    date_str=date_str,
                    payload={
                        "status": "no_trade",
                        "reasoning": reasoning,
                        "plan": plan_snapshot,
                        "llm_audit": llm_audit,
                        "orders": [],
                        "positions_after": self.positions,
                        "cash_after": self.cash,
                        "market_session": market_session,
                        "run_start_ts": run_start_ts,
                    },
                )
                return

            market_session = get_market_session(
                datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")),
                MARKET_TIMEZONE,
                RTH_START,
                RTH_END,
                HALF_DAY_RTH_END,
            )
            metrics["rth_ok"] = bool(market_session.get("can_place_orders"))
            metrics["market_state"] = market_session.get("market_state")
            metrics["market_reason"] = market_session.get("session_reason")
            metrics["market_half_day"] = bool(market_session.get("is_half_day"))
            metrics["market_rth_end"] = market_session.get("effective_rth_end")
            planning_reason = None
            if ENFORCE_RTH and not ALLOW_OUTSIDE_RTH and not bool(market_session.get("can_place_orders")):
                planning_reason = str(market_session.get("session_reason") or "out_of_window")
            else:
                planning_reason = get_submission_guard_reason(BROKER_TYPE, ENABLE_LIVE_TRADING)
            if planning_reason:
                logger.warning(f"⏸️ 当前仅允许生成计划，不会下单（{planning_reason}）。")
                emit_event("agent", "WARN", "planning_only", planning_reason, {"date": date_str, "market_session": market_session})
                log_struct("planning_only", {"date": date_str, "broker": BROKER_TYPE, "reason": planning_reason}, level="WARNING")
                status = "planning_only"
                SnapshotDB().save_decision(
                    date_str=date_str,
                    payload={
                        "status": "planning_only",
                        "reasoning": reasoning,
                        "plan": plan_snapshot,
                        "llm_audit": llm_audit,
                        "orders": proposed_orders,
                        "positions_after": self.positions,
                        "cash_after": self.cash,
                        "market_session": market_session,
                        "planning_only_reason": planning_reason,
                        "live_trading_enabled": bool(ENABLE_LIVE_TRADING),
                        "run_start_ts": run_start_ts,
                    },
                )
                return
            
            # 5. 执行订单并同步账本
            before_cash = float(self.cash)
            before_positions = dict(self.positions)
            t_submit0 = time.perf_counter()
            execution_report = self.broker.submit_orders(proposed_orders) or []
            metrics["submit_sec"] = round(time.perf_counter() - t_submit0, 6)

            def _classify_execution(report: list) -> dict:
                if not isinstance(report, list) or len(report) == 0:
                    return {"status": "submitted_no_report", "requested": 0, "filled": 0}

                requested = 0
                filled = 0
                status_counts = {}
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

            execution_summary = _classify_execution(execution_report)

            after_cash = None
            after_positions = None
            t_rec0 = time.perf_counter()
            for _ in range(3):
                after_cash, after_positions = self.broker.get_account_summary()
                rec = reconcile_execution(before_cash, before_positions, float(after_cash), dict(after_positions), execution_report)
                if rec.get("ok"):
                    break
                time.sleep(1.0)
            metrics["reconcile_sec"] = round(time.perf_counter() - t_rec0, 6)

            self.cash, self.positions = after_cash, after_positions
            
            logger.info(f"\n✅ 今日调仓完毕！对账完成，最新现金余额: ${self.cash:,.2f}")
            logger.info(f"📊 最新真实持仓: {self.positions}")
            
            PortfolioDB().save_state(self.cash, self.positions)

            reconciliation = reconcile_execution(before_cash, before_positions, float(self.cash), dict(self.positions), execution_report)
            metrics["reconcile_ok"] = bool(reconciliation.get("ok"))
            if not reconciliation.get("ok"):
                logger.warning(f"⚠️ [对账差异] 成交回报与账户持仓不一致: {reconciliation.get('mismatched')}")
                log_struct("reconcile_mismatch", {"date": date_str, "broker": BROKER_TYPE, "mismatched": reconciliation.get("mismatched")}, level="WARNING")
            else:
                log_struct("reconcile_ok", {"date": date_str, "broker": BROKER_TYPE})

            ExecutionLedger().save(
                date_str=date_str,
                payload={
                    "before": {"cash": before_cash, "positions": before_positions},
                    "orders": proposed_orders,
                    "execution_report": execution_report,
                    "after": {"cash": self.cash, "positions": self.positions},
                    "reconciliation": reconciliation,
                },
            )

            SnapshotDB().save_decision(
                date_str=date_str,
                payload={
                    "status": execution_summary.get("status"),
                    "reasoning": reasoning,
                    "plan": plan_snapshot,
                    "llm_audit": llm_audit,
                    "orders": proposed_orders,
                    "execution_report": execution_report,
                    "execution_summary": execution_summary,
                    "reconciliation": reconciliation,
                    "positions_after": self.positions,
                    "cash_after": self.cash,
                    "market_session": market_session,
                    "run_start_ts": run_start_ts,
                },
            )
            status = execution_summary.get("status") or "traded"
            
        except Exception as e:
            # 记录严重错误，并直接触发熔断锁死，防止下次定时任务在异常状态下继续跑
            fatal_error = str(e)
            self.trigger_kill_switch(
                str(e),
                source="agent.exception",
                trigger_event={"date": date_str, "broker": BROKER_TYPE, "run_mode": self.run_mode},
            )
            logger.error(f"❌ 交易执行过程中发生致命错误，已熔断: {e}", exc_info=True)
            status = "exception"
            raise
        finally:
            run_end_ts = datetime.utcnow().isoformat() + "Z"
            metrics["status"] = status
            metrics["total_sec"] = round(time.perf_counter() - t0, 6)
            metrics["run_end_ts"] = run_end_ts
            heartbeat_store.finish_run(
                str(heartbeat_run.get("run_id") or ""),
                status=status,
                error=fatal_error,
                extra={
                    "date": str(metrics.get("date") or date_str),
                    "broker": BROKER_TYPE,
                    "run_mode": self.run_mode,
                    "live_trading_enabled": bool(ENABLE_LIVE_TRADING),
                    "market_state": metrics.get("market_state"),
                    "total_sec": metrics.get("total_sec"),
                },
            )
            if metrics.get("date") is not None:
                MetricsDB().append(metrics)
                decision = SnapshotDB().load_decision(str(metrics.get("date")))
                notify_result = evaluate_and_notify(
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
                        SnapshotDB().save_decision(
                            date_str=str(metrics.get("date")),
                            payload={**(decision.get("payload") or {}), "kill_switch_reason": reason},
                        )
                    self.trigger_kill_switch(
                        f"alert_policy:{reason}",
                        source="alert.policy",
                        trigger_event={
                            "date": str(metrics.get("date")),
                            "broker": BROKER_TYPE,
                            "status": str(metrics.get("status")),
                            "policy_items": notify_result.get("items"),
                        },
                    )
