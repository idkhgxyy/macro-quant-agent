"""Daily agent entrypoint: acquires run lock, configures broker, instantiates MacroQuantAgent and calls run_daily_routine()."""

import argparse
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from utils.logger import setup_logger
logger = setup_logger(__name__)
from config import (
    ALPHA_VANTAGE_KEY, VOLCENGINE_API_KEY, VOLCENGINE_MODEL_ENDPOINT,
    LLM_BASE_URL,
    TECH_UNIVERSE, INITIAL_CAPITAL, BROKER_TYPE, ENABLE_LIVE_TRADING, IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID,
    MARKET_TIMEZONE, RTH_END,
)
from data.cache import PortfolioDB
from data.retriever import RAGRetriever
from llm.volcengine import VolcengineLLMClient
from execution.broker import MockBroker, IBKRBroker
from core.agent import MacroQuantAgent
from core.planning import PlanningService
from core.execution import ExecutionService as ExecutionSvc
from core.persistence import PersistenceService
from core.ops import OpsService
from utils.heartbeat import HeartbeatStore
from utils.run_lock import RunLock


class _DemoRetriever:
    """Retriever that returns plausible mock data without any API calls."""

    def fetch_macro_data(self) -> str:
        return "- VIX 恐慌指数: 18.0\n- 10年期美债收益率: 4.10%\n- 美元指数: 104.2"

    def fetch_fundamental_data(self) -> str:
        return "- AAPL: 当前市盈率(PE) 25.0, 远期PE 22.5\n- MSFT: PE 30.2\n- NVDA: PE 55.0"

    def fetch_news(self) -> str:
        return "标题: 科技股情绪稳定\n摘要: 市场风险偏好平稳，AI 板块持续受到关注。"

    def fetch_market_data(self) -> dict:
        return {
            "context_string": "- AAPL: 当前价格 $195.50, 近一月涨跌幅 +3.00%\n- MSFT: $420.00, +2.10%",
            "prices": {ticker: 100.0 + hash(ticker) % 400 for ticker in TECH_UNIVERSE},
        }

    def fetch_filing_data(self) -> dict:
        return {
            "context_string": "- AAPL: 8-K on 2026-06-10 (Apple Inc.)",
            "evidence": [
                {
                    "source": "sec_edgar",
                    "ticker": "AAPL",
                    "quote": "8-K filed on 2026-06-10 for AAPL (Apple Inc.).",
                    "chunk_id": "sec:AAPL:8-K:2026-06-10:0",
                    "url": "https://www.sec.gov/Archives/example/aapl-8k.htm",
                    "timestamp": "2026-06-10T13:30:00Z",
                }
            ],
            "source": "sec_edgar_recent_filings",
        }

    def get_provider_status(self) -> dict:
        return {
            "market": {"selected_provider": "demo", "mode": "fresh", "detail": "demo_mode"},
            "filing": {"selected_provider": "demo", "mode": "fresh", "detail": "demo_mode"},
        }


class _DemoLLM:
    """LLM client that returns a plausible allocation plan without any API calls."""

    def generate_retrieval_route(self, **_kwargs) -> dict:
        return {
            "focus_sources": ["positions", "market", "sec_edgar"],
            "avoid_sources": [],
            "rationale": "Demo 模式：关注持仓、行情和公告",
            "_audit": {"prompt_version": "demo", "model_endpoint": "demo-llm"},
        }

    def generate_strategy(self, *_args, **_kwargs) -> dict:
        return {
            "reasoning": "Demo 模式：增配 AAPL 和 NVDA，维持 MSFT 底仓",
            "selected_strategies": ["core_hold_momentum_tilt"],
            "allocations": {"AAPL": 0.18, "MSFT": 0.15, "NVDA": 0.17, "cash": 0.50},
            "evidence_weights": {"news": 0.4, "market": 0.3, "sec_edgar": 0.3},
            "self_evaluation": {"confidence": 0.72, "key_risks": ["AI 板块估值偏高"], "counterpoints": ["若利率下行，成长股有支撑"]},
            "evidence": [
                {"source": "news", "quote": "市场风险偏好平稳。", "ticker": "AAPL"},
                {"source": "market", "quote": "NVDA 近一月涨跌幅 +8.5%", "ticker": "NVDA"},
            ],
            "_valid": True,
            "_errors": [],
            "_warnings": [],
            "_audit": {"prompt_version": "demo", "model_endpoint": "demo-llm"},
        }


def validate_config():
    required_vars = {
        "ALPHA_VANTAGE_KEY": "数据检索（Alpha Vantage）",
        "VOLCENGINE_API_KEY": "LLM 策略生成（Volcengine）",
    }
    missing = []
    for var, purpose in required_vars.items():
        value = globals().get(var)
        if not value:
            missing.append(f"  - {var}（用于 {purpose}）")
    if missing:
        logger.warning("缺少以下环境变量，部分功能可能受限：\n" + "\n".join(missing))
    else:
        logger.info("✅ 关键环境变量校验通过。")
    return len(missing) == 0


def build_agent(run_mode: str = "manual", demo: bool = False) -> MacroQuantAgent:
    # 1. 实例化各个独立模块
    if demo:
        logger.info("🎮 [Demo 模式] 使用模拟数据，不需要任何 API Key")
        retriever = _DemoRetriever()
        llm_client = _DemoLLM()
    else:
        retriever = RAGRetriever(alpha_vantage_key=ALPHA_VANTAGE_KEY)
        llm_client = VolcengineLLMClient(
            api_key=VOLCENGINE_API_KEY,
            model_endpoint=VOLCENGINE_MODEL_ENDPOINT,
            base_url=LLM_BASE_URL,
        )

    # 2. 根据配置选择 Broker (Mock 还是 IBKR)
    if BROKER_TYPE == "ibkr" and not demo:
        logger.info(f"🔌 [系统配置] 已切换至 IBKR 实盘/仿真模式 (端口: {IBKR_PORT})")
        if not ENABLE_LIVE_TRADING:
            logger.warning("🔒 [安全模式] ENABLE_LIVE_TRADING 未开启；本次运行只会生成计划，不会向 IBKR 提交订单。")
        my_broker = IBKRBroker(host=IBKR_HOST, port=IBKR_PORT, client_id=IBKR_CLIENT_ID)
    else:
        if demo:
            logger.info("🎮 [Demo 模式] 使用 Mock Broker，初始资金 $100,000")
        else:
            logger.info("🎮 [系统配置] 当前处于 Mock 本地回测模拟模式")
        default_positions = {ticker: 0 for ticker in TECH_UNIVERSE}
        saved_cash, saved_positions = PortfolioDB().load_state(INITIAL_CAPITAL, default_positions)

        my_broker = MockBroker(initial_cash=saved_cash)
        my_broker.server_positions = saved_positions

    # 3. 实例化核心服务层
    planning_service = PlanningService(llm_client=llm_client, retriever=retriever)
    execution_service = ExecutionSvc(broker=my_broker)
    persistence_service = PersistenceService()
    ops_service = OpsService()

    # 4. 实例化核心智能体
    return MacroQuantAgent(
        llm_client=llm_client,
        retriever=retriever,
        broker=my_broker,
        run_mode=run_mode,
        planning_service=planning_service,
        execution_service=execution_service,
        persistence_service=persistence_service,
        ops_service=ops_service,
    )


def main(run_mode: str = "manual", demo: bool = False):
    if demo:
        logger.info("=== LLM 科技股量化决策引擎 V6.0 — Demo 模式 ===\n")
        logger.info("📋 Demo 模式说明：")
        logger.info("   - 使用模拟数据，不需要任何 API Key")
        logger.info("   - 绕过市场时段检查，随时可运行")
        logger.info("   - 所有交易在 Mock Broker 中模拟执行，无真实资金风险")
        logger.info("   - 要使用真实数据，请配置 .env 后运行 python3 run_agent.py\n")
    else:
        logger.info("=== LLM 科技股量化决策引擎 V6.0 (实盘 Broker 统一版) ===\n")
    date_str = datetime.now(ZoneInfo(MARKET_TIMEZONE)).date().isoformat()
    owner_id = uuid.uuid4().hex
    heartbeat_store = HeartbeatStore()
    run_lock = RunLock()
    lock_result = run_lock.acquire(
        owner_id=owner_id,
        run_mode=run_mode,
        date_str=date_str,
        heartbeat_store=heartbeat_store,
    )
    if not lock_result.get("acquired"):
        existing = lock_result.get("existing") if isinstance(lock_result.get("existing"), dict) else {}
        logger.warning(
            "⏸️ 检测到已有 daily agent 正在运行，跳过本次启动。"
            f" pid={existing.get('pid')} host={existing.get('host')} acquired_at={existing.get('acquired_at')}"
        )
        return {"status": "already_running", "lock": lock_result}
    if lock_result.get("stale_recovered"):
        logger.warning("♻️ 检测到陈旧运行锁，已自动清理并继续本次启动。")

    try:
        if not demo:
            validate_config()
        agent = build_agent(run_mode=run_mode, demo=demo)

        # Demo 模式下绕过市场时段检查
        if demo:
            from unittest.mock import patch as _patch
            with _patch("core.agent.get_market_session", return_value={
                "market_state": "rth",
                "session_reason": "demo_mode",
                "is_trading_day": True,
                "is_half_day": False,
                "can_place_orders": True,
                "effective_rth_end": RTH_END,
            }):
                logger.info("="*40 + " [Demo 交易循环启动] " + "="*40)
                result = agent.run_daily_routine()
        else:
            logger.info("\n" + "="*40 + " [今日交易循环启动] " + "="*40)
            result = agent.run_daily_routine()

        if demo:
            logger.info("\n" + "="*40 + " [Demo 运行完成] " + "="*40)
            logger.info("📊 查看结果: python3 dashboard/server.py")
            logger.info("🌐 浏览器访问: http://127.0.0.1:8010/")
            logger.info("💡 要使用真实数据，请编辑 .env 文件后运行: python3 run_agent.py")
        return result
    finally:
        if not run_lock.release(owner_id):
            logger.warning("⚠️ 本次运行结束后未能确认释放运行锁，请检查 runtime/agent_run.lock。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Macro Quant Agent — LLM 驱动的科技股量化决策引擎")
    parser.add_argument("--demo", action="store_true", help="Demo 模式：使用模拟数据，不需要 API Key，绕过市场时段检查")
    args = parser.parse_args()
    main(demo=args.demo)
