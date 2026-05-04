from utils.logger import setup_logger
logger = setup_logger(__name__)

import os
from config import (
    ALPHA_VANTAGE_KEY, VOLCENGINE_API_KEY, VOLCENGINE_MODEL_ENDPOINT, 
    TECH_UNIVERSE, INITIAL_CAPITAL, BROKER_TYPE, ENABLE_LIVE_TRADING, IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
)
from data.cache import PortfolioDB
from data.retriever import RAGRetriever
from llm.volcengine import VolcengineLLMClient
from execution.broker import MockBroker, IBKRBroker
from core.agent import MacroQuantAgent


def build_agent(run_mode: str = "manual") -> MacroQuantAgent:
    # 1. 实例化各个独立模块
    retriever = RAGRetriever(alpha_vantage_key=ALPHA_VANTAGE_KEY)
    llm_client = VolcengineLLMClient(api_key=VOLCENGINE_API_KEY, model_endpoint=VOLCENGINE_MODEL_ENDPOINT)

    # 2. 根据配置选择 Broker (Mock 还是 IBKR)
    if BROKER_TYPE == "ibkr":
        logger.info(f"🔌 [系统配置] 已切换至 IBKR 实盘/仿真模式 (端口: {IBKR_PORT})")
        if not ENABLE_LIVE_TRADING:
            logger.warning("🔒 [安全模式] ENABLE_LIVE_TRADING 未开启；本次运行只会生成计划，不会向 IBKR 提交订单。")
        my_broker = IBKRBroker(host=IBKR_HOST, port=IBKR_PORT, client_id=IBKR_CLIENT_ID)
    else:
        logger.info("🎮 [系统配置] 当前处于 Mock 本地回测模拟模式")
        default_positions = {ticker: 0 for ticker in TECH_UNIVERSE}
        saved_cash, saved_positions = PortfolioDB().load_state(INITIAL_CAPITAL, default_positions)

        my_broker = MockBroker(initial_cash=saved_cash)
        my_broker.server_positions = saved_positions

    # 3. 实例化核心智能体
    return MacroQuantAgent(llm_client=llm_client, retriever=retriever, broker=my_broker, run_mode=run_mode)


def main(run_mode: str = "manual"):
    logger.info("=== LLM 科技股量化决策引擎 V6.0 (实盘 Broker 统一版) ===\n")
    agent = build_agent(run_mode=run_mode)

    # 4. 运行今日交易循环
    logger.info("\n" + "="*40 + " [今日交易循环启动] " + "="*40)
    return agent.run_daily_routine()


if __name__ == "__main__":
    main()
