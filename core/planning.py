"""PlanningService: RAG retrieval, LLM strategy generation, and portfolio rebalancing.

Replaces the planning-related phases of MacroQuantAgent._gather_context()
and _make_plan() with an injectable service. The old methods remain in
agent.py for backward compatibility during incremental migration.
"""
import time
from typing import Optional

from config import ALLOW_OUTSIDE_RTH, BROKER_TYPE
from data.retriever import RAGRetriever
from execution.portfolio import PortfolioManager
from llm.volcengine import VolcengineLLMClient
from utils.logger import setup_logger
from utils.structlog import log_struct

logger = setup_logger(__name__)


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


def get_submission_guard_reason(broker_type: str, enable_live_trading: bool) -> Optional[str]:
    if str(broker_type).lower() == "ibkr" and not bool(enable_live_trading):
        return "live_trading_disabled"
    return None


class PlanningService:
    """Middleware between Data/Layer and Execution/Layer — handles everything
    from raw context retrieval through LLM planning to trade-order generation.

    This service is stateless: all runtime state (cash, positions, market session)
    is passed as parameters. The caller (MacroQuantAgent or tests) owns the
    orchestration and persistence concerns.
    """

    def __init__(self, llm_client: VolcengineLLMClient, retriever: RAGRetriever):
        self.llm = llm_client
        self.retriever = retriever

    def retrieve_context(
        self,
        cash: float,
        positions: dict[str, float],
        market_session: dict,
        date_str: str,
        run_mode: str,
    ) -> dict:
        """Fetch all data sources and generate a retrieval route.

        Returns a context dict with ``success`` set to False when
        critical data (prices) is unavailable.
        """
        t_rag0 = time.perf_counter()
        macro_data = self.retriever.fetch_macro_data()
        fundamental_data = self.retriever.fetch_fundamental_data()
        news_data = self.retriever.fetch_news()
        market_data_dict = self.retriever.fetch_market_data()
        filing_data = self.retriever.fetch_filing_data()
        rag_sec = round(time.perf_counter() - t_rag0, 6)
        provider_status = self.retriever.get_provider_status()
        log_struct("rag_provider_status", provider_status)

        market_context_str = market_data_dict["context_string"]
        current_prices = market_data_dict["prices"]
        filing_context_str = filing_data.get("context_string", "") if isinstance(filing_data, dict) else str(filing_data)

        if not current_prices:
            logger.warning("无法获取最新价格，跳过调仓。")
            log_struct("daily_abort_no_prices", {"date": date_str, "broker": BROKER_TYPE}, level="WARNING")
            return {"success": False, "status": "abort_no_prices"}

        # 检测缺价 ticker，从决策池中排除
        missing_price_tickers = [t for t in positions if current_prices.get(t) is None]
        if missing_price_tickers:
            logger.warning(f"⚠️ 以下 ticker 缺少价格数据，将从决策池中排除: {missing_price_tickers}")

        portfolio_value = float(cash)
        for ticker, shares in positions.items():
            portfolio_value += float(shares) * float(current_prices.get(ticker, 0))

        current_summary = [f"现金: ${cash:,.2f} ({cash/portfolio_value*100:.1f}%)"]
        for ticker, shares in positions.items():
            val = float(shares) * float(current_prices.get(ticker, 0))
            weight = val / portfolio_value if portfolio_value > 0 else 0
            current_summary.append(f"{ticker}: {int(shares)}股, 价值 ${val:,.2f} ({weight*100:.1f}%)")
        current_positions_str = "\n".join(current_summary)

        retrieval_route = self.llm.generate_retrieval_route(
            news_context=news_data,
            market_context=market_context_str,
            macro_context=macro_data,
            fundamental_context=fundamental_data,
            current_positions_summary=current_positions_str,
            filing_context=filing_context_str,
            provider_status=provider_status,
            mode=run_mode,
        )
        retrieval_route_context = _format_retrieval_route_context(retrieval_route)

        logger.info("-" * 60)
        logger.info("📂 【RAG 组装完毕】")
        logger.info(f"【当前持仓】:\n{current_positions_str}\n")
        logger.info(f"【宏观】:\n{macro_data}\n")
        logger.info(f"【基本面】:\n{fundamental_data}\n")
        logger.info(f"【市场】:\n{market_context_str}\n")
        logger.info(f"【新闻】:\n{news_data[:200]}...\n")
        logger.info(f"【SEC 公告】:\n{filing_context_str}\n")
        logger.info(f"【检索路由】:\n{retrieval_route_context or '默认综合评估'}\n")
        logger.info("-" * 60)

        return {
            "success": True,
            "rag_sec": rag_sec,
            "macro_data": macro_data,
            "fundamental_data": fundamental_data,
            "news_data": news_data,
            "market_data_dict": market_data_dict,
            "filing_data": filing_data,
            "provider_status": provider_status,
            "market_context_str": market_context_str,
            "current_prices": current_prices,
            "filing_context_str": filing_context_str,
            "portfolio_value": portfolio_value,
            "current_positions_str": current_positions_str,
            "retrieval_route": retrieval_route,
            "retrieval_route_context": retrieval_route_context,
            "missing_price_tickers": missing_price_tickers,
        }

    def generate_plan(
        self,
        cash: float,
        positions: dict[str, float],
        ctx: dict,
        date_str: str,
        run_mode: str,
    ) -> Optional[dict]:
        """Generate an LLM strategy, validate it, and produce trade orders.

        Returns a plan dict with orders and metadata, or None when the
        strategy is invalid or no orders are needed.
        """
        t_llm0 = time.perf_counter()
        strategy_plan = self.llm.generate_strategy(
            ctx["news_data"],
            ctx["market_context_str"],
            ctx["macro_data"],
            ctx["fundamental_data"],
            ctx["current_positions_str"],
            filing_context=ctx["filing_context_str"],
            retrieval_route_context=ctx["retrieval_route_context"],
        )
        llm_sec = round(time.perf_counter() - t_llm0, 6)

        reasoning = strategy_plan.get("reasoning", "无理由")
        target_weights: dict = strategy_plan.get("allocations", {})
        is_valid = bool(strategy_plan.get("_valid", True))
        errors: list = strategy_plan.get("_errors", [])
        warnings: list = strategy_plan.get("_warnings", [])
        strategy_ids: list = strategy_plan.get("selected_strategies", [])
        llm_audit: dict = strategy_plan.get("_audit", {}) if isinstance(strategy_plan.get("_audit", {}), dict) else {}
        plan_snapshot: dict = {k: v for k, v in strategy_plan.items() if not str(k).startswith("_")}
        cash_ratio = float(cash) / float(ctx["portfolio_value"]) if float(ctx["portfolio_value"]) > 0 else 0.0

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
            logger.error(f"LLM 输出未通过校验，错误: {errors}")
            log_struct("llm_invalid_skip_trade", {"date": date_str, "broker": BROKER_TYPE, "errors": errors}, level="WARNING")
            return {
                "success": False,
                "status": "invalid",
                "reasoning": reasoning,
                "plan_snapshot": plan_snapshot,
                "llm_audit": llm_audit,
                "retrieval_route": ctx["retrieval_route"],
                "orders": [],
                "target_weights": target_weights,
                "strategy_ids": strategy_ids,
                "errors": errors,
                "warnings": warnings,
                "llm_sec": llm_sec,
                "cash_ratio": cash_ratio,
            }

        t_reb0 = time.perf_counter()
        proposed_orders = PortfolioManager.rebalance(cash, positions, target_weights, ctx["current_prices"])
        rebalance_sec = round(time.perf_counter() - t_reb0, 6)

        turnover_ratio = 0.0
        if ctx["portfolio_value"] > 0:
            turnover_ratio = sum(float(o.get("amount", 0.0) or 0.0) for o in proposed_orders) / float(ctx["portfolio_value"])

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
            logger.info("仓位已达标，无需调仓。")
            log_struct("no_trade", {"date": date_str, "broker": BROKER_TYPE, "cash_ratio": round(cash_ratio, 6)})
            return {
                "success": True,
                "status": "no_trade",
                "reasoning": reasoning,
                "plan_snapshot": plan_snapshot,
                "llm_audit": llm_audit,
                "retrieval_route": ctx["retrieval_route"],
                "orders": [],
                "target_weights": target_weights,
                "strategy_ids": strategy_ids,
                "errors": errors,
                "warnings": warnings,
                "llm_sec": llm_sec,
                "rebalance_sec": rebalance_sec,
                "turnover_ratio": turnover_ratio,
                "cash_ratio": cash_ratio,
            }

        return {
            "success": True,
            "status": "ready",
            "reasoning": reasoning,
            "plan_snapshot": plan_snapshot,
            "llm_audit": llm_audit,
            "retrieval_route": ctx["retrieval_route"],
            "proposed_orders": proposed_orders,
            "target_weights": target_weights,
            "strategy_ids": strategy_ids,
            "errors": errors,
            "warnings": warnings,
            "llm_sec": llm_sec,
            "rebalance_sec": rebalance_sec,
            "turnover_ratio": round(turnover_ratio, 6),
            "cash_ratio": round(cash_ratio, 6),
        }
